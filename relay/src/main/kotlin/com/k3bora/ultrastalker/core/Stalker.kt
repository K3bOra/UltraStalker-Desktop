package com.k3bora.ultrastalker.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import okhttp3.Headers
import okhttp3.OkHttpClient
import okhttp3.Request
import java.net.URI
import java.net.URLEncoder

/* A Stalker (MAG) portal, asked exactly like the website and the receiver ask it. */
class Stalker(override val source: Source, private val http: OkHttpClient) : Provider {
    companion object {
        const val UA = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG254 stbapp ver: 4 rev: 272 Safari/533.3"
        const val XUA = "Model: MAG254; Link: Ethernet"

        fun endpoints(url: String): List<String> {
            val u = try {
                URI(url.trim())
            } catch (_: Exception) {
                return emptyList()
            }
            val port = if (u.port > 0) ":${u.port}" else ""
            val base = "${u.scheme}://${u.host}$port"
            val path = (u.path ?: "").trimEnd('/')
            val low = path.lowercase()
            val c = mutableListOf<String>()
            if (low.endsWith("portal.php") || low.endsWith("server/load.php")) c += base + path
            if (low.contains("stalker_portal")) c += base + path.substring(0, low.indexOf("stalker_portal")).trimEnd('/') + "/stalker_portal/server/load.php"
            if (low.endsWith("/c")) c += base + path.dropLast(2) + "/server/load.php"
            c += listOf("$base/portal.php", "$base/server/load.php", "$base/stalker_portal/server/load.php")
            return c.distinct().take(5)
        }

        fun rows(js: JsonElement?): List<JsonObject> {
            if (js is JsonArray) return js.mapNotNull { it as? JsonObject }
            if (js is JsonObject) for (k in listOf("data", "items", "channels", "results")) (js[k] as? JsonArray)?.let { a -> return a.mapNotNull { it as? JsonObject } }
            return emptyList()
        }

        fun flag(v: String) = v.trim().lowercase() in setOf("1", "true", "yes", "on")

        fun stripWrapper(v: String): String {
            var t = v.trim().removeSurrounding("\"").removeSurrounding("'")
            if (t.isEmpty()) return ""
            val parts = t.split(" ")
            if (parts.size > 1 && parts[0].lowercase() in setOf("ffmpeg", "auto")) t = parts.drop(1).joinToString(" ").trim()
            Regex("(https?|rtmp|rtsp|udp|rtp)://\\S+", RegexOption.IGNORE_CASE).find(t)?.let { t = it.value }
            return t.removeSurrounding("\"").removeSurrounding("'")
        }

        fun seasonNumber(s: JsonObject, fallback: String): String {
            val sid = s.s("id", "season_id")
            if (sid.contains(":")) sid.substringAfterLast(":").takeIf { it.isNotEmpty() }?.let { return it }
            return s.s("season", "season_number").ifEmpty { fallback }
        }
    }

    private val mac = source.mac
    @Volatile private var endpoint = ""
    @Volatile private var token = ""
    @Volatile private var random = ""
    private val lock = Any()

    private fun identity(): Map<String, String> {
        val sn = hash("MD5", mac).uppercase().take(13)
        val deviceId = hash("SHA-256", mac).uppercase()
        return mapOf(
            "sn" to sn, "deviceId" to deviceId, "deviceId2" to hash("SHA-256", deviceId).uppercase(),
            "hw2" to hash("SHA-1", mac), "prehash" to hash("SHA-1", sn + mac), "signature" to hash("SHA-256", deviceId + deviceId).uppercase(),
        )
    }

    fun headers(tok: String): Map<String, String> {
        val h = linkedMapOf("User-Agent" to UA, "X-User-Agent" to XUA, "Cookie" to "mac=$mac; stb_lang=en; timezone=Europe%2FLondon", "Accept" to "*/*")
        try {
            val u = URI(source.portal)
            h["Referer"] = "${u.scheme}://${u.host}${if (u.port > 0) ":${u.port}" else ""}/"
        } catch (_: Exception) {
        }
        if (tok.isNotEmpty()) h["Authorization"] = "Bearer $tok"
        return h
    }

    private class Answer(val js: JsonElement?, val text: String)

    private fun raw(ep: String, params: Map<String, String>, tok: String): Answer {
        val q = params.entries.joinToString("&") { (k, v) -> URLEncoder.encode(k, "UTF-8") + "=" + URLEncoder.encode(v, "UTF-8") }
        val url = ep + (if (ep.contains("?")) "&" else "?") + q
        val hb = Headers.Builder()
        headers(tok).forEach { (k, v) -> hb.set(k, v) }
        val res = http.newCall(Request.Builder().url(url).headers(hb.build()).build()).execute()
        val text = res.use { it.body?.string() ?: "" }
        if (!res.isSuccessful) {
            if (res.code == 401 || res.code == 403) throw ProviderError("Portal answered ${res.code}", res.code)
            if (text.isEmpty()) throw ProviderError("Portal answered ${res.code}")
        }
        val obj = parseLoose(text) ?: run {
            if (Regex("authoriz|token", RegexOption.IGNORE_CASE).containsMatchIn(text)) throw ProviderError("invalid token", 401)
            throw ProviderError("Portal sent an unreadable answer")
        }
        val js = if (obj is JsonObject && obj.containsKey("js")) obj["js"] else obj
        return Answer(js, text)
    }

    private fun handshakeOn(ep: String): Pair<String, String> {
        val tries = listOf(
            mapOf("type" to "stb", "action" to "handshake", "token" to "", "JsHttpRequest" to "1-xml"),
            mapOf("type" to "stb", "action" to "handshake", "token" to "", "mac" to mac, "JsHttpRequest" to "1-xml"),
        )
        for (p in tries) {
            try {
                val js = raw(ep, p, "").js as? JsonObject
                val t = js?.s("token") ?: ""
                if (t.isNotEmpty()) return t to js!!.s("random")
            } catch (e: ProviderError) {
                if (e.status == 403 || e.status == 504) throw e
            } catch (_: Exception) {
            }
        }
        val fake = hash("SHA-1", Math.random().toString() + System.nanoTime()).take(32).uppercase()
        val js = raw(ep, mapOf("type" to "stb", "action" to "handshake", "JsHttpRequest" to "1-xml", "mac" to mac, "prehash" to hash("SHA-1", fake)), fake).js as? JsonObject
        val t = js?.s("token") ?: ""
        if (t.isNotEmpty()) return t to js!!.s("random")
        throw ProviderError("The portal refused this MAC address", 401)
    }

    fun profileParams(full: Boolean): Map<String, String> {
        val id = identity()
        val ts = (System.currentTimeMillis() / 1000).toString()
        if (!full) return mapOf("type" to "stb", "action" to "get_profile", "JsHttpRequest" to "1-xml", "sn" to id["sn"]!!, "device_id" to "", "timestamp" to ts)
        return linkedMapOf(
            "type" to "stb", "action" to "get_profile", "JsHttpRequest" to "1-xml", "hd" to "1",
            "ver" to "ImageDescription: 0.2.18-r23-254; PORTAL version: 5.3.0; API Version: JS API version: 343; STB API version: 146; Player Engine version: 0x58c",
            "num_banks" to "2", "sn" to id["sn"]!!, "stb_type" to "MAG254", "client_type" to "STB", "image_version" to "218", "video_out" to "hdmi",
            "device_id" to id["deviceId"]!!, "device_id2" to id["deviceId2"]!!, "signature" to id["signature"]!!, "auth_second_step" to "1",
            "hw_version" to "2.6-IB-00", "not_valid_token" to "0",
            "metrics" to jsonOf("type" to "STB", "model" to "MAG254", "mac" to mac, "sn" to id["sn"], "uid" to "", "random" to random).toString(),
            "hw_version_2" to id["hw2"]!!, "timestamp" to ts, "api_signature" to "262", "prehash" to id["prehash"]!!,
        )
    }

    fun authorize(force: Boolean = false) = synchronized(lock) {
        if (token.isNotEmpty() && !force) return@synchronized
        val list = if (endpoint.isNotEmpty()) listOf(endpoint) + endpoints(source.portal).filter { it != endpoint } else endpoints(source.portal)
        var last: Exception? = null
        for (ep in list) {
            try {
                val (t, r) = handshakeOn(ep)
                endpoint = ep
                token = t
                random = r
                var prof: JsonObject? = null
                for (full in listOf(true, false)) {
                    try {
                        val js = raw(ep, profileParams(full), token).js as? JsonObject
                        if (js != null) {
                            prof = js
                            if (!(Regex("error", RegexOption.IGNORE_CASE).containsMatchIn(js.s("msg")) && js.s("play_token").isEmpty())) break
                        }
                    } catch (e: ProviderError) {
                        if (e.status == 401) break
                    } catch (_: Exception) {
                    }
                }
                if (prof != null && prof.s("status") == "2" && Regex("block", RegexOption.IGNORE_CASE).containsMatchIn(prof.s("msg"))) throw ProviderError("The portal says this account is blocked", 403)
                return@synchronized
            } catch (e: Exception) {
                last = e
                if (e is ProviderError && e.status == 403 && e.message?.contains("block") == true) throw e
            }
        }
        throw (last as? ProviderError) ?: ProviderError("Portal unreachable" + (last?.message?.let { " ($it)" } ?: ""))
    }

    fun call(params: Map<String, String>): JsonElement? {
        authorize()
        for (attempt in 0..1) {
            val out = try {
                raw(endpoint, params, token)
            } catch (e: ProviderError) {
                if (e.status == 401 && attempt == 0) {
                    authorize(true)
                    continue
                }
                throw e
            }
            val bad = (out.js == null || out.js is JsonNull) && Regex("authoriz|invalid token|access denied", RegexOption.IGNORE_CASE).containsMatchIn(out.text)
            if (bad && attempt == 0) {
                authorize(true)
                continue
            }
            return out.js
        }
        throw ProviderError("Portal session expired", 401)
    }

    private fun prefix(): String = (endpoint.ifEmpty { endpoints(source.portal).firstOrNull() ?: "" }).replace(Regex("server/load\\.php$|portal\\.php$", RegexOption.IGNORE_CASE), "")

    fun art(row: JsonObject, media: Media): String {
        val base = prefix().ifEmpty { source.portal }
        fun pick(vararg k: String) = k.map { row.s(it) }.firstOrNull { it.isNotEmpty() && it != "0" } ?: ""
        if (media == Media.LIVE) {
            var logo = pick("logo", "logo_url", "picon")
            if (logo.isNotEmpty() && !Regex("^(https?:)?/", RegexOption.IGNORE_CASE).containsMatchIn(logo) && !logo.contains("/")) logo = "misc/logos/320/$logo"
            return if (logo.isEmpty()) "" else resolveUrl(base, logo)
        }
        val v = pick("screenshot_uri", "cover_big", "cover", "poster", "poster_url", "logo")
        return if (v.isEmpty()) "" else resolveUrl(base, v)
    }

    private fun categoryRows(media: Media, action: String): List<JsonObject> {
        for (sortby in listOf(false, true)) {
            val p = linkedMapOf("type" to media.api, "action" to action, "JsHttpRequest" to "1-xml")
            if (sortby) p["sortby"] = "number"
            val js = call(p)
            val r = rows(js)
            if (r.isNotEmpty() || js is JsonArray) return r
        }
        return emptyList()
    }

    override fun categories(media: Media): List<Category> {
        val label = { r: JsonObject -> r.s("title", "name", "category_name", "genre_name", "label", "alias") }
        var r: List<JsonObject>
        if (media == Media.LIVE) {
            r = categoryRows(media, "get_genres")
            // some portals answer get_genres with short routing labels: their folders are in get_categories
            val counts = r.groupingBy { label(it).lowercase() }.eachCount()
            if (r.size >= 8 && counts.any { (k, n) -> n >= 3 && k.length <= 4 }) {
                val alt = runCatching { categoryRows(media, "get_categories") }.getOrDefault(emptyList())
                if (alt.map(label).toSet().size > r.map(label).toSet().size) r = alt
            }
        } else {
            r = categoryRows(media, "get_categories")
            if (r.isEmpty()) r = categoryRows(media, "get_genres")
        }
        return r.mapNotNull { row ->
            val id = row.s("id", "category_id", "genre_id")
            val t = label(row)
            if (id.isEmpty() || t.isEmpty() || Adult.row(row) || Adult.text(t)) null else Category(id, t)
        }
    }

    private fun listParams(media: Media, category: String, page: Int): LinkedHashMap<String, String> {
        val p = linkedMapOf("type" to media.api, "action" to "get_ordered_list", "p" to page.toString(), "JsHttpRequest" to "1-xml")
        when (media) {
            Media.LIVE -> {
                p["genre"] = category
                p["force_ch_link_check"] = "0"
            }
            Media.MOVIES -> p["category"] = category
            Media.SERIES -> p.putAll(mapOf("movie_id" to "0", "season_id" to "0", "episode_id" to "0", "category" to category))
        }
        return p
    }

    fun toItem(row: JsonObject, media: Media): Item {
        val id = row.s("id", "ch_id", "movie_id", "series_id").ifEmpty { row.s("cmd").hashCode().toString() }
        val title = row.s("name", "title", "o_name").ifEmpty { if (media == Media.LIVE) "Channel" else "Untitled" }
        return Item(
            id = id, title = title, media = media, image = art(row, media), number = row.s("number", "num"),
            year = row.s("year").take(4), rating = row.s("rating_imdb", "rating_kinopoisk", "rating").takeIf { it != "0" && it != "N/A" } ?: "",
            plot = row.s("description", "descr", "plot"), raw = row,
        )
    }

    override fun page(media: Media, category: String, page: Int): Page {
        var js: JsonElement? = null
        var r: List<JsonObject> = emptyList()
        for (sortby in listOf(false, true)) {
            val p = listParams(media, category, page)
            if (sortby) p["sortby"] = "number"
            js = call(p)
            r = rows(js)
            if (r.isNotEmpty()) break
        }
        val meta = js as? JsonObject
        val total = meta?.s("total_items", "total")?.toIntOrNull() ?: 0
        val per = meta?.s("max_page_items", "page_size")?.toIntOrNull()?.takeIf { it > 0 } ?: r.size.coerceAtLeast(1)
        val items = r.filterNot { Adult.row(it) }.map { toItem(it, media) }
        return Page(items, total, r.isNotEmpty() && (if (total > 0) page * per < total else r.size >= per))
    }

    /* ------------------------------------------------------------------ series */
    private fun rowIdentity(row: JsonObject, i: Int): String {
        val ep = row.s("episode_id", "episode")
        if (ep.isNotEmpty()) return "episode|" + row.s("season", "season_number", "season_id") + "|" + ep + "|" + row.s("id")
        val n = seasonNumber(row, "")
        if (n.isNotEmpty()) return "season|$n"
        if (row.s("season_id").isNotEmpty()) return "season_id|" + row.s("season_id")
        if (row.s("id").isNotEmpty()) return "id|" + row.s("id")
        return "row|" + row.s("name", "title") + "|" + i
    }

    private fun merge(vararg lists: List<JsonObject>): List<JsonObject> {
        val m = LinkedHashMap<String, JsonObject>()
        for (l in lists) l.forEachIndexed { i, row ->
            val k = rowIdentity(row, i)
            val prev = m[k]
            if (prev == null) m[k] = row
            else m[k] = JsonObject(prev + row.filter { (_, v) -> !(v is JsonNull || (v is JsonPrimitive && v.contentOrNull.isNullOrEmpty()) || (v is JsonArray && v.isEmpty())) })
        }
        return m.values.toList()
    }

    private fun suspicious(r: List<JsonObject>): Boolean {
        if (r.isEmpty()) return true
        if (r.any { it.s("episode_id", "episode").isNotEmpty() }) return false
        val nums = r.mapIndexedNotNull { i, s -> seasonNumber(s, (i + 1).toString()).substringAfterLast(":").toIntOrNull() }
        if (nums.isEmpty()) return false
        val u = nums.distinct().sorted()
        if (u.first() > 1) return true
        return u.size != u.last() - u.first() + 1
    }

    private fun seriesRowsOnce(sid: String, page: Int?): List<JsonObject> {
        val p = linkedMapOf("type" to "series", "action" to "get_ordered_list", "movie_id" to sid, "season_id" to "0", "episode_id" to "0", "JsHttpRequest" to "1-xml")
        if (page != null) {
            p["p"] = page.toString()
            p["page"] = page.toString()
        }
        return rows(call(p))
    }

    private fun seriesRows(sid: String): List<JsonObject> {
        val fresh = seriesRowsOnce(sid, null)
        var combined = merge(fresh)
        if (suspicious(fresh)) {
            runCatching { combined = merge(combined, seriesRowsOnce(sid, null)) }
            var seen = combined.size
            for (page in 1 until 5) {
                val r = runCatching { seriesRowsOnce(sid, page) }.getOrNull() ?: break
                if (r.isEmpty()) break
                val merged = merge(combined, r)
                if (merged.size <= seen) break
                combined = merged
                seen = combined.size
                if (!suspicious(combined)) break
            }
        }
        if (combined.any { (it["series"] as? JsonArray)?.isNotEmpty() == true }) {
            combined = combined.filter { (it["series"] as? JsonArray)?.isNotEmpty() == true || (it["episodes"] as? JsonArray)?.isNotEmpty() == true || it.s("id").contains(":") }
        }
        return combined
    }

    override fun seasons(series: Item): List<Season> {
        val sid = series.raw.s("series_id", "id", "movie_id").ifEmpty { series.id }
        val r = seriesRows(sid)
        var result = r.mapIndexed { i, row ->
            val id = row.s("id", "season_id").ifEmpty { "$sid:${i + 1}" }
            val number = seasonNumber(row, (i + 1).toString())
            row.plus("id" to id, "season_id" to id, "season" to number, "parent_series_id" to sid, "name" to row.s("name").ifEmpty { "Season $number" })
        }
        if (result.isNotEmpty() && result.none { it["series"] is JsonArray } && result.any { it.s("episode", "episode_id").isNotEmpty() }) {
            result = result.groupBy { it.s("season", "season_id").ifEmpty { "1" } }.map { (n, eps) ->
                jsonOf("id" to "$sid:$n", "season_id" to "$sid:$n", "season" to n, "name" to "Season $n", "episodes" to JsonArray(eps), "parent_series_id" to sid)
            }
        }
        return result.map { s ->
            Season(s.s("id"), seasonNumber(s, "1"), s.s("name"), episodes(series, sid, s), s)
        }
    }

    private fun episodes(series: Item, sid: String, season: JsonObject): List<Item> {
        val seasonId = season.s("id", "season_id").ifEmpty { "$sid:1" }
        val number = seasonNumber(season, "1")
        val values = ((season["episodes"] as? JsonArray)?.takeIf { it.isNotEmpty() } ?: season["series"] as? JsonArray) ?: return emptyList()
        val command = season.s("cmd", "command", "url")
        return values.mapIndexed { i, v ->
            val epObj = v as? JsonObject
            val epId = epObj?.s("episode_id", "episode", "number", "episode_num", "episode_number", "id")?.ifEmpty { null } ?: (v as? JsonPrimitive)?.contentOrNull ?: (i + 1).toString()
            var ep = epObj ?: JsonObject(emptyMap())
            if (ep.s("cmd").isEmpty()) ep = ep.plus("cmd" to command)
            ep = ep.plus("id" to epId, "episode_id" to epId, "episode" to epId, "number" to epId, "season" to number, "season_id" to seasonId, "stream_id" to seasonId, "movie_id" to sid, "name" to ep.s("name").ifEmpty { "Episode $epId" })
            Item(id = "$seasonId/$epId", title = ep.s("name"), media = Media.SERIES, image = art(ep, Media.SERIES).ifEmpty { series.image }, number = epId, plot = ep.s("description").ifEmpty { series.plot }, raw = ep)
        }
    }

    /* ------------------------------------------------------------------ links */
    private fun vodMediaCommand(row: JsonObject, media: Media): String {
        val command = row.s("cmd", "command", "url")
        if (!command.startsWith("/media/")) return command
        val sid = row.s("stream_id", "season_id", "id", "movie_id")
        if (sid.isEmpty()) return command
        try {
            val r = rows(call(linkedMapOf("type" to (if (media == Media.MOVIES) "vod" else "series"), "action" to "get_ordered_list", "movie_id" to sid, "season_id" to "0", "episode_id" to "0", "category" to "1", "sortby" to "", "p" to "1", "JsHttpRequest" to "1-xml")))
            val mid = r.firstOrNull()?.s("id") ?: ""
            if (mid.isNotEmpty()) {
                val last = command.substringBefore("?").substringAfterLast("/")
                val ext = if (last.contains(".")) "." + last.substringAfterLast(".") else ""
                return "/media/file_$mid$ext"
            }
        } catch (_: Exception) {
        }
        return command
    }

    private fun cleanLive(v: String): String {
        val t = stripWrapper(v).replace(Regex("%mac%", RegexOption.IGNORE_CASE), mac)
        return try {
            val u = URI(t)
            if (u.scheme?.lowercase() !in setOf("http", "https", "rtmp", "rtsp", "udp", "rtp")) ""
            else if (u.host?.lowercase() in setOf("localhost", "127.0.0.1", "::1") || t.lowercase().contains("///")) ""
            else t
        } catch (_: Exception) {
            ""
        }
    }

    /* the relay's /play ticket: it asks the portal for a fresh link each time VLC opens it */
    override fun ticket(item: Item, seriesNumber: String?): JsonObject {
        authorize()
        val row = item.raw
        var raw = row.s("cmd", "command", "url")
        if (item.media != Media.LIVE) raw = vodMediaCommand(row, item.media)
        raw = raw.removeSurrounding("\"").removeSurrounding("'")
        if (raw.isEmpty()) throw ProviderError("This item has no stream", 404)
        val streamHeaders = jsonOf("User-Agent" to UA)
        val base = mutableMapOf<String, JsonElement>(
            "mode" to JsonPrimitive("stalker"), "endpoint" to JsonPrimitive(endpoint), "headers" to JsonObject(headers("").mapValues { JsonPrimitive(it.value) }),
            "token" to JsonPrimitive(token), "mac" to JsonPrimitive(mac),
            "handshake" to jsonOf("type" to "stb", "action" to "handshake", "token" to "", "JsHttpRequest" to "1-xml"),
            "profile" to JsonObject(profileParams(true).mapValues { JsonPrimitive(it.value) }), "streamHeaders" to streamHeaders,
        )
        if (item.media == Media.LIVE) {
            val meta = listOf("use_http_tmp_link", "use_load_balancing", "disable_ad").any { row.containsKey(it) }
            val force = flag(row.s("force_ch_link_check"))
            val low = raw.lowercase()
            val needs = if (meta) flag(row.s("use_http_tmp_link")) || flag(row.s("use_load_balancing")) || force
            else force || low.contains("localhost") || low.contains("///") || low.contains("/ch/") || !low.contains("http")
            val direct = cleanLive(raw)
            if (!needs && direct.isNotEmpty()) return jsonOf("mode" to "direct", "u" to direct, "h" to streamHeaders, "ext" to if (direct.contains(".m3u8", true)) "m3u8" else "ts")
            base["create"] = jsonOf("type" to "itv", "action" to "create_link", "cmd" to raw, "series" to "0", "forced_storage" to "0", "disable_ad" to if (flag(row.s("disable_ad"))) "1" else "0", "download" to "0", "force_ch_link_check" to if (force) "1" else "0", "JsHttpRequest" to "1-xml")
            base["fallback"] = JsonPrimitive(direct)
            base["ext"] = JsonPrimitive(if (raw.contains("m3u8", true)) "m3u8" else "ts")
            return JsonObject(base)
        }
        val directFallback = stripWrapper(raw)
        val directOk = Regex("^(https?|rtmp|rtsp)://", RegexOption.IGNORE_CASE).containsMatchIn(directFallback) && !Regex("localhost|///", RegexOption.IGNORE_CASE).containsMatchIn(raw)
        val ext = Regex("\\.(mp4|mkv|avi|m4v|mov|ts|m3u8)$", RegexOption.IGNORE_CASE).find(raw.substringBefore("?"))?.groupValues?.get(1)?.lowercase() ?: "mp4"
        val num = seriesNumber ?: if (item.media == Media.SERIES) row.s("episode", "episode_id") else null
        base["create"] = jsonOf("type" to "vod", "action" to "create_link", "cmd" to raw, "series" to (num ?: ""), "forced_storage" to "", "disable_ad" to "0", "download" to "0", "force_ch_link_check" to "0", "JsHttpRequest" to "1-xml")
        val alt = row.s("id").takeIf { item.media == Media.SERIES && it.isNotEmpty() && it != num }
        if (alt != null) base["altSeries"] = JsonPrimitive(alt)
        base["fallback"] = JsonPrimitive(if (directOk) directFallback else "")
        base["ext"] = JsonPrimitive(ext)
        return JsonObject(base)
    }
}

package com.k3bora.ultrastalker.relay

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.Headers
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.net.URI
import java.net.URLEncoder
import java.security.SecureRandom
import java.util.Base64
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit

/* The relay of the Ultra Stalker website (worker/src/index.js), in Kotlin, for the TV.

   The page can't send a portal's MAC cookie or User-Agent itself, so it asks this relay:
     /p?u=<url>&h=<headers>   one request with those headers (also posters and HLS)
     POST /ticket             "how to get this channel's link" → /play/<id>.<ext>
     /play/<id>.<ext>         the stream: a fresh portal link each time it is opened
   It runs inside the TV app, so portals are reached from the home connection itself. */

data class Upstream(val status: Int, val headers: Headers, val body: java.io.InputStream?, val finalUrl: String, val response: Response?)

data class Reply(
    val status: Int,
    val headers: Map<String, String>,
    val body: java.io.InputStream? = null,
    val length: Long = -1,
) {
    companion object {
        fun json(status: Int, obj: JsonElement, extra: Map<String, String> = emptyMap()): Reply {
            val bytes = obj.toString().toByteArray()
            return Reply(status, CORS + mapOf("Content-Type" to "application/json; charset=utf-8", "Cache-Control" to "no-store") + extra, bytes.inputStream(), bytes.size.toLong())
        }
        fun text(status: Int, text: String, type: String = "text/plain; charset=utf-8", extra: Map<String, String> = emptyMap()): Reply {
            val bytes = text.toByteArray()
            return Reply(status, mapOf("Content-Type" to type) + extra, bytes.inputStream(), bytes.size.toLong())
        }
        val CORS = mapOf(
            "Access-Control-Allow-Origin" to "*",
            "Access-Control-Allow-Methods" to "GET, HEAD, POST, OPTIONS",
            "Access-Control-Allow-Headers" to "Range, Content-Type",
            "Access-Control-Expose-Headers" to "Content-Length, Content-Range, Content-Type, X-Final-Url, X-Upstream-Status",
        )
    }
}

class Relay(
    private val client: OkHttpClient = defaultClient(),
    private val cloudRelay: String = "https://ultrastalker-web.k3borazz0.workers.dev",
) {
    companion object {
        val PASS_REQ = listOf("range", "if-range", "if-none-match", "if-modified-since")
        val PASS_RES = listOf("content-type", "content-length", "content-range", "accept-ranges", "etag", "last-modified", "cache-control", "expires")
        const val UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
        private val random = SecureRandom()

        fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .followRedirects(true)
            .followSslRedirects(true)
            .retryOnConnectionFailure(true)
            .build()

        fun enc(s: String): String = URLEncoder.encode(s, "UTF-8").replace("+", "%20")

        fun b64urlDecode(text: String): String {
            val s = text.replace('-', '+').replace('_', '/')
            val pad = if (s.length % 4 != 0) "=".repeat(4 - s.length % 4) else ""
            return String(Base64.getDecoder().decode(s + pad), Charsets.UTF_8)
        }

        fun extOf(url: String): String = try {
            val m = Regex("\\.(m3u8|ts|mp4|mkv|avi|m4v|mov|webm|mp3|aac)$", RegexOption.IGNORE_CASE).find(URI(url).path ?: "")
            m?.groupValues?.get(1)?.lowercase() ?: "ts"
        } catch (_: Exception) {
            "ts"
        }

        fun looksLikePlaylist(url: String, type: String): Boolean {
            if (type.lowercase().contains("mpegurl")) return true
            return try {
                Regex("\\.m3u8$", RegexOption.IGNORE_CASE).containsMatchIn(URI(url).path ?: "")
            } catch (_: Exception) {
                false
            }
        }

        fun resolveUrl(base: String, ref: String): String = try {
            URI(base).resolve(ref.trim().replace(" ", "%20")).toString()
        } catch (_: Exception) {
            ref
        }

        /* the "h" headers (JSON object) without the ones a relay must not pass */
        fun cleanHeaders(raw: JsonObject?): Headers {
            val b = Headers.Builder()
            raw?.forEach { (k, v) ->
                val key = k.trim()
                if (key.isEmpty() || Regex("^(host|origin|referer|cf-|x-forwarded|x-real-ip|content-length)", RegexOption.IGNORE_CASE).containsMatchIn(key)) return@forEach
                val value = (v as? JsonPrimitive)?.contentOrNull ?: v.toString()
                try {
                    b.set(key, value)
                } catch (_: IllegalArgumentException) {
                    b.set(key, value.filter { it.code in 0x20..0x7e })
                }
            }
            if (b.get("User-Agent") == null) b.set("User-Agent", UA)
            if (b.get("Accept") == null) b.set("Accept", "*/*")
            return b.build()
        }

        fun stripPlayer(v: String?, mac: String?): String {
            var t = (v ?: "").trim().removeSurrounding("\"").removeSurrounding("'")
            val first = t.split(" ").firstOrNull()?.lowercase() ?: ""
            if (first == "ffmpeg" || first == "auto") t = t.substring(first.length).trim()
            Regex("(https?|rtmp|rtsp)://\\S+", RegexOption.IGNORE_CASE).find(t)?.let { t = it.value }
            if (!mac.isNullOrEmpty()) t = t.replace(Regex("%mac%", RegexOption.IGNORE_CASE), mac)
            return t
        }

        fun newId(): String {
            val bytes = ByteArray(12)
            random.nextBytes(bytes)
            return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes).replace("-", "x").replace("_", "y")
        }
    }

    /* ------------------------------------------------------------------ upstream */
    fun fetch(url: String, headers: Headers, method: String = "GET", body: ByteArray? = null): Upstream {
        val req = Request.Builder().url(url).headers(headers)
        when (method) {
            "POST" -> req.post((body ?: ByteArray(0)).toRequestBody(null))
            "HEAD" -> req.head()
            else -> req.get()
        }
        // byte ranges must stay byte ranges
        if (headers["Range"] != null && headers["Accept-Encoding"] == null) req.header("Accept-Encoding", "identity")
        val res = client.newCall(req.build()).execute()
        return Upstream(res.code, res.headers, res.body?.byteStream(), res.request.url.toString(), res)
    }

    private fun passHeaders(up: Upstream): MutableMap<String, String> {
        val out = LinkedHashMap(Reply.CORS)
        for (name in PASS_RES) up.headers[name]?.let { out[name] = it }
        return out
    }

    /* ------------------------------------------------------------------ /p */
    fun proxy(query: Map<String, String>, method: String, reqHeaders: Map<String, String>, body: ByteArray?, self: String): Reply {
        val u = query["u"] ?: ""
        val h = query["h"] ?: ""
        if (!Regex("^https?://", RegexOption.IGNORE_CASE).containsMatchIn(u)) return Reply.json(400, buildJsonObject { put("error", "bad url") })
        val extra: JsonObject? = if (h.isNotEmpty()) {
            try {
                Json.parseToJsonElement(b64urlDecode(h)).jsonObject
            } catch (_: Exception) {
                return Reply.json(400, buildJsonObject { put("error", "bad headers") })
            }
        } else null
        val hb = cleanHeaders(extra).newBuilder()
        for (name in PASS_REQ) reqHeaders[name]?.let { hb.set(name, it) }
        val up = try {
            fetch(u, hb.build(), if (method == "HEAD") "HEAD" else method, if (method == "POST") body else null)
        } catch (e: Exception) {
            return Reply.json(502, buildJsonObject { put("error", "unreachable"); put("detail", (e.message ?: e.toString()).take(160)) })
        }
        val out = passHeaders(up)
        out["X-Final-Url"] = up.finalUrl
        out["X-Upstream-Status"] = up.status.toString()
        val type = up.headers["content-type"] ?: ""
        val ok = up.status in 200..299
        if (ok && type.startsWith("image/", true)) out["cache-control"] = "public, max-age=604800"
        if (method != "HEAD" && ok && looksLikePlaylist(up.finalUrl, type)) {
            val text = up.response?.body?.string() ?: ""
            if (text.trimStart().startsWith("#EXTM3U") && text.contains("#EXT-X-")) {
                out.remove("content-length")
                out["content-type"] = "application/vnd.apple.mpegurl"
                out["cache-control"] = "no-store"
                val rewritten = rewrite(text, up.finalUrl) { abs -> "$self/p?u=${enc(abs)}" + (if (h.isNotEmpty()) "&h=${enc(h)}" else "") }
                return Reply(up.status, out, rewritten.toByteArray().inputStream(), rewritten.toByteArray().size.toLong())
            }
            out.remove("content-length")
            return Reply(up.status, out, text.toByteArray().inputStream(), text.toByteArray().size.toLong())
        }
        if (method == "HEAD") up.response?.close()
        return Reply(up.status, out, if (method == "HEAD") null else up.body, up.headers["content-length"]?.toLongOrNull() ?: -1)
    }

    private fun rewrite(text: String, base: String, wrap: (String) -> String): String =
        text.split(Regex("\r?\n")).joinToString("\n") { line ->
            val t = line.trim()
            when {
                t.isEmpty() -> line
                t.startsWith("#") -> Regex("URI=\"([^\"]+)\"").replace(line) { "URI=\"" + wrap(resolveUrl(base, it.groupValues[1])) + "\"" }
                else -> wrap(resolveUrl(base, t))
            }
        }

    /* ------------------------------------------------------------------ tickets */
    private class Ticket(val data: JsonObject, val at: Long = System.currentTimeMillis())
    private val tickets = object : LinkedHashMap<String, Ticket>(64, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Ticket>?) = size > 2000
    }
    private fun keep(data: JsonObject): String {
        val id = newId()
        synchronized(tickets) { tickets[id] = Ticket(data) }
        return id
    }
    private fun ticket(id: String): JsonObject? = synchronized(tickets) {
        val t = tickets[id] ?: return null
        if (System.currentTimeMillis() - t.at > 24 * 3600_000L) {
            tickets.remove(id)
            null
        } else t.data
    }

    fun makeTicket(body: ByteArray?, self: String): Reply {
        val d = try {
            if ((body?.size ?: 0) > 24000) throw IllegalArgumentException("too big")
            Json.parseToJsonElement(String(body ?: ByteArray(0))).jsonObject
        } catch (_: Exception) {
            return Reply.json(400, buildJsonObject { put("error", "bad ticket request") })
        }
        val mode = d.str("mode")
        when (mode) {
            "direct" -> if (!Regex("^https?://", RegexOption.IGNORE_CASE).containsMatchIn(d.str("u"))) return Reply.json(400, buildJsonObject { put("error", "bad url") })
            "stalker" -> if (!Regex("^https?://", RegexOption.IGNORE_CASE).containsMatchIn(d.str("endpoint")) || d["create"] == null) return Reply.json(400, buildJsonObject { put("error", "bad portal") })
            else -> return Reply.json(400, buildJsonObject { put("error", "bad mode") })
        }
        val id = keep(d)
        val ext = (d.str("ext").ifEmpty { if (mode == "direct") extOf(d.str("u")) else "ts" }).replace(Regex("[^a-zA-Z0-9]"), "").take(5).ifEmpty { "ts" }
        return Reply.json(200, buildJsonObject { put("ok", true); put("url", "$self/play/$id.$ext") })
    }

    /* the app asks for a ticket directly (no HTTP round trip) */
    fun ticketUrl(d: JsonObject, self: String): String {
        val r = makeTicket(d.toString().toByteArray(), self)
        val js = Json.parseToJsonElement(r.body?.use { String(it.readBytes()) } ?: "{}").jsonObject
        return js.str("url").ifEmpty { throw IllegalArgumentException(js.str("error").ifEmpty { "bad ticket" }) }
    }

    private fun portalCall(d: JsonObject, params: JsonObject, token: String): JsonElement? {
        val endpoint = d.str("endpoint")
        val q = params.entries.joinToString("&") { (k, v) -> enc(k) + "=" + enc((v as? JsonPrimitive)?.contentOrNull ?: v.toString()) }
        val url = endpoint + (if (endpoint.contains("?")) "&" else "?") + q
        val raw = (d["headers"] as? JsonObject)?.toMutableMap() ?: mutableMapOf()
        if (token.isNotEmpty()) raw["Authorization"] = JsonPrimitive("Bearer $token")
        val up = fetch(url, cleanHeaders(JsonObject(raw)))
        val text = up.response?.use { it.body?.string() } ?: ""
        val obj = try {
            Json.parseToJsonElement(text.removePrefix("﻿"))
        } catch (_: Exception) {
            null
        }
        return if (obj is JsonObject && obj.containsKey("js")) obj["js"] else obj
    }

    /* a fresh stream link from the portal; sign in again if the saved session ended */
    fun stalkerLink(d: JsonObject): String {
        var why = ""
        val mac = d.str("mac")
        fun tryLink(token: String, series: String?): String {
            val params = (d["create"] as? JsonObject)?.toMutableMap() ?: mutableMapOf()
            if (series != null) params["series"] = JsonPrimitive(series)
            val js = portalCall(d, JsonObject(params), token)
            val value = when (js) {
                is JsonObject -> listOf("cmd", "url", "link").firstNotNullOfOrNull { (js[it] as? JsonPrimitive)?.contentOrNull?.takeIf { s -> s.isNotEmpty() } }
                is JsonPrimitive -> js.contentOrNull
                else -> null
            }
            if (js is JsonObject && js["error"] != null) why = js.str("error").take(120)
            val clean = stripPlayer(value, mac)
            return if (Regex("^(https?|rtmp|rtsp)://", RegexOption.IGNORE_CASE).containsMatchIn(clean) && !Regex("//(localhost|127\\.0\\.0\\.1)[:/]", RegexOption.IGNORE_CASE).containsMatchIn(clean)) clean else ""
        }
        fun attempt(token: String): String {
            var link = tryLink(token, null)
            val alt = d["altSeries"]
            if (link.isEmpty() && alt != null && alt !is kotlinx.serialization.json.JsonNull) link = tryLink(token, (alt as? JsonPrimitive)?.contentOrNull ?: alt.toString())
            return link
        }
        var link = if (d.str("token").isNotEmpty()) runCatching { attempt(d.str("token")) }.getOrDefault("") else ""
        if (link.isEmpty() && d["handshake"] is JsonObject) {
            val hs = runCatching { portalCall(d, d["handshake"] as JsonObject, "") }.getOrNull()
            val token = (hs as? JsonObject)?.str("token") ?: ""
            if (token.isNotEmpty()) {
                if (d["profile"] is JsonObject) runCatching { portalCall(d, d["profile"] as JsonObject, token) }
                link = runCatching { attempt(token) }.getOrDefault("")
            }
        }
        if (link.isEmpty() && d.str("fallback").isNotEmpty()) link = d.str("fallback")
        if (link.isEmpty()) throw IllegalStateException("The portal did not give a stream link" + if (why.isNotEmpty()) " ($why)" else "")
        return link
    }

    /* A movie is read in many pieces: a portal link is reused while it works (3 hours),
       a live link only briefly; a refused link is replaced at once. */
    private class Cached(val link: String, val at: Long)
    private val links = ConcurrentHashMap<String, Cached>()

    fun play(id: String, query: Map<String, String>, method: String, reqHeaders: Map<String, String>, self: String): Reply {
        val d = ticket(id) ?: return Reply.text(403, "This link expired. Open it again from Ultra Stalker.", extra = Reply.CORS)
        val stalker = d.str("mode") == "stalker"
        val raw = (if (stalker) d["streamHeaders"] else d["h"]) as? JsonObject
        val hb = cleanHeaders(raw).newBuilder()
        for (name in PASS_REQ) reqHeaders[name]?.let { hb.set(name, it) }
        val headers = hb.build()
        val live = (d["create"] as? JsonObject)?.str("type") == "itv"
        val ttl = if (live) 20_000L else 3 * 3600_000L
        var up: Upstream? = null
        var problem = ""
        for (round in 0..1) {
            val reused = if (stalker && round == 0 && !query.containsKey("fresh")) links[id]?.takeIf { System.currentTimeMillis() - it.at < ttl }?.link ?: "" else ""
            val target = try {
                if (stalker) reused.ifEmpty { stalkerLink(d) } else d.str("u")
            } catch (e: Exception) {
                return Reply.text(502, e.message ?: "portal error", extra = Reply.CORS)
            }
            up = try {
                fetch(target, headers, if (method == "HEAD") "HEAD" else "GET")
            } catch (e: Exception) {
                problem = "Stream server unreachable"
                null
            }
            if (up != null && up.status < 400) {
                if (stalker) links[id] = Cached(target, System.currentTimeMillis())
                break
            }
            if (up != null) {
                problem = "Stream server answered ${up.status}"
                if (stalker) up.response?.close()
            }
            links.remove(id)
            if (!stalker) break
        }
        val res = up ?: return Reply.text(502, problem, extra = Reply.CORS)
        val out = passHeaders(res)
        out["cache-control"] = "no-store"
        val type = res.headers["content-type"] ?: ""
        if (method != "HEAD" && res.status in 200..299 && looksLikePlaylist(res.finalUrl, type)) {
            val text = res.response?.body?.string() ?: ""
            if (text.trimStart().startsWith("#EXTM3U")) {
                val rewritten = rewrite(text, res.finalUrl) { abs ->
                    val seg = buildJsonObject {
                        put("mode", "direct")
                        put("u", abs)
                        if (raw != null) put("h", raw)
                    }
                    "$self/play/${keep(seg)}.${extOf(abs)}"
                }
                out.remove("content-length")
                out["content-type"] = "application/vnd.apple.mpegurl"
                return Reply(res.status, out, rewritten.toByteArray().inputStream(), rewritten.toByteArray().size.toLong())
            }
            out.remove("content-length")
            return Reply(res.status, out, text.toByteArray().inputStream(), text.toByteArray().size.toLong())
        }
        if (method == "HEAD") res.response?.close()
        return Reply(res.status, out, if (method == "HEAD") null else res.body, res.headers["content-length"]?.toLongOrNull() ?: -1)
    }

    /* artwork lookups: the online relay keeps the TMDB key */
    fun tmdb(pathAndQuery: String): Reply = try {
        val up = fetch(cloudRelay + pathAndQuery, Headers.headersOf("Origin", "https://k3bora.github.io", "Accept", "application/json", "User-Agent", UA))
        val bytes = up.response?.use { it.body?.bytes() } ?: ByteArray(0)
        Reply(up.status, mapOf("Content-Type" to (up.headers["content-type"] ?: "application/json"), "Cache-Control" to "max-age=3600"), bytes.inputStream(), bytes.size.toLong())
    } catch (e: Exception) {
        Reply.json(502, buildJsonObject { put("error", "tmdb unreachable") })
    }

    fun health(): Reply = Reply.json(200, buildJsonObject { put("ok", true); put("service", "ultrastalker-tv"); put("tickets", true); put("tmdb", false) })
}

internal fun JsonObject.str(key: String): String = (this[key] as? JsonPrimitive)?.contentOrNull ?: ""

package com.k3bora.ultrastalker.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.File
import java.net.URI
import java.net.URLDecoder
import java.net.URLEncoder
import java.security.MessageDigest
import java.util.zip.ZipInputStream

/* Sources: the receiver's profiles.json and portals.txt rules, the TV's own list, and
   the receiver's backup ZIP. */
object Sources {
    private val MAC = Regex("^[0-9A-F]{2}(:[0-9A-F]{2}){5}$")

    fun canonicalMac(v: String?): String {
        val hex = (v ?: "").uppercase().filter { it in "0123456789ABCDEF" }
        if (hex.length != 12) return ""
        return hex.chunked(2).joinToString(":")
    }

    /* the website's and the receiver's made-up MAC for playlists (same key everywhere) */
    fun syntheticMac(portal: String): String = ("02" + hash("SHA-1", portal).substring(0, 10)).uppercase().chunked(2).joinToString(":")

    fun looksLikeM3u(v: String): Boolean {
        val low = v.trim().lowercase()
        if (low.startsWith("file://") || low.startsWith("m3u://") || low.startsWith("m3u8://")) return true
        val path = try {
            URI(v.trim()).path?.lowercase() ?: ""
        } catch (_: Exception) {
            low
        }
        if (path.endsWith(".m3u") || path.endsWith(".m3u8")) return true
        if (path.endsWith("/get.php") || path.endsWith("/player_api.php")) return low.contains("username=") && low.contains("password=")
        return low.contains("type=m3u") || low.contains("output=m3u")
    }

    fun xtreamUrl(host: String, user: String, pass: String): String {
        val h = host.trim().trimEnd('/').let { if (Regex("^https?://", RegexOption.IGNORE_CASE).containsMatchIn(it)) it else "http://$it" }
        val e = { s: String -> URLEncoder.encode(s, "UTF-8") }
        return "$h/get.php?username=${e(user)}&password=${e(pass)}&type=m3u_plus&output=ts"
    }

    fun xtreamCreds(portal: String): Triple<String, String, String>? = try {
        val u = URI(portal)
        val q = (u.rawQuery ?: "").split("&").mapNotNull { p ->
            val i = p.indexOf('=')
            if (i <= 0) null else p.substring(0, i) to URLDecoder.decode(p.substring(i + 1), "UTF-8")
        }.toMap()
        val user = q["username"].orEmpty()
        val pass = q["password"].orEmpty()
        if (user.isEmpty() || pass.isEmpty()) null
        else {
            val path = (u.rawPath ?: "").replace(Regex("/(get|player_api)\\.php$", RegexOption.IGNORE_CASE), "").trimEnd('/')
            val port = if (u.port > 0) ":${u.port}" else ""
            Triple("${u.scheme}://${u.host}$port$path", user, pass)
        }
    } catch (_: Exception) {
        null
    }

    /* one receiver-style row (profiles.json / the website) → a source */
    fun fromRow(row: JsonObject): Source? {
        var portal = row.s("portal").trimEnd('.', ',', ';')
        if (portal.isEmpty()) return null
        if (portal.startsWith("file://", true)) return null // a playlist on the receiver's disk
        var stype = row.s("source_type").lowercase().ifEmpty { if (looksLikeM3u(portal)) "m3u" else "stalker" }
        if (stype == "m3u") {
            if (portal.startsWith("m3u://", true)) portal = "http://" + portal.substring(6)
            else if (portal.startsWith("m3u8://", true)) portal = "http://" + portal.substring(7)
        }
        if (!Regex("^https?://", RegexOption.IGNORE_CASE).containsMatchIn(portal)) portal = "http://$portal"
        try {
            if (URI(portal).host.isNullOrEmpty()) return null
        } catch (_: Exception) {
            return null
        }
        val name = row.s("name").take(80)
        if (stype != "m3u") {
            val mac = canonicalMac(row.s("mac"))
            if (!MAC.matches(mac)) return null
            return Source(name, portal, mac, SourceKind.PORTAL)
        }
        val mode = row.s("playlist_mode").lowercase()
        val low = portal.lowercase()
        val xtream = mode == "xtream" || (mode != "m3u" && (low.contains("get.php") || low.contains("player_api.php") || low.contains("username=")) && low.contains("password="))
        return Source(name, portal, syntheticMac(portal), if (xtream && xtreamCreds(portal) != null) SourceKind.XTREAM else SourceKind.M3U)
    }

    fun toRow(s: Source): JsonObject = buildJsonObject {
        put("name", s.name)
        put("portal", s.portal)
        put("mac", s.mac)
        put("source", "tv")
        when (s.kind) {
            SourceKind.PORTAL -> put("source_type", "stalker")
            SourceKind.XTREAM -> {
                put("source_type", "m3u")
                put("playlist_mode", "xtream")
            }
            SourceKind.M3U -> {
                put("source_type", "m3u")
                put("playlist_mode", "m3u")
            }
        }
    }

    /* portals.txt: a portal URL followed by its MACs, M3U links, Xtream logins */
    fun parseText(text: String): List<Source> {
        val out = mutableListOf<Source>()
        var current = ""
        var xBase = ""
        var xUser = ""
        var xPass = ""
        fun flushXt() {
            if (xBase.isNotEmpty() && xUser.isNotEmpty() && xPass.isNotEmpty()) fromRow(JsonObject(mapOf("portal" to JsonPrimitive(xtreamUrl(xBase, xUser, xPass)), "source_type" to JsonPrimitive("m3u"), "playlist_mode" to JsonPrimitive("xtream"))))?.let { out += it }
            xBase = ""
            xUser = ""
            xPass = ""
        }
        for (raw in text.split(Regex("\r?\n"))) {
            val line = raw.trim()
            if (line.isEmpty()) {
                flushXt()
                current = ""
                continue
            }
            if (line.startsWith("#") || line.startsWith(";") || line.startsWith("//")) continue
            fun lab(n: String) = Regex("\\b$n\\s*[:=]\\s*(\\S+)", RegexOption.IGNORE_CASE).find(line)?.groupValues?.get(1) ?: ""
            val user = lab("username").ifEmpty { lab("user") }
            val pass = lab("password").ifEmpty { lab("pass") }
            val url = Regex("https?://[^\\s\"'<>]+", RegexOption.IGNORE_CASE).find(line)?.value?.trimEnd('.', ',', ';') ?: ""
            if (url.isNotEmpty() && looksLikeM3u(url)) {
                fromRow(JsonObject(mapOf("portal" to JsonPrimitive(url), "source_type" to JsonPrimitive("m3u"))))?.let { out += it }
                continue
            }
            if (user.isNotEmpty() || pass.isNotEmpty()) {
                if (url.isNotEmpty()) xBase = url else if (xBase.isEmpty() && current.isNotEmpty()) xBase = current
                if (user.isNotEmpty()) xUser = user
                if (pass.isNotEmpty()) xPass = pass
                if (xBase.isNotEmpty() && xUser.isNotEmpty() && xPass.isNotEmpty()) flushXt()
                continue
            }
            if (url.isNotEmpty()) current = url
            if (current.isNotEmpty()) {
                for (m in Regex("[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}").findAll(line)) {
                    fromRow(JsonObject(mapOf("portal" to JsonPrimitive(current), "mac" to JsonPrimitive(m.value), "source_type" to JsonPrimitive("stalker"))))?.let { out += it }
                }
            }
        }
        flushXt()
        return out
    }

    fun dedupe(list: List<Source>): List<Source> {
        val seen = HashSet<String>()
        return list.filter { seen.add(it.key) }
    }

    /* ------------------------------------------------------------------ the receiver's backup */
    class BackupError(message: String) : Exception(message)

    data class Restored(val sources: List<Source>, val receiverOnly: Int)

    private val ALLOWED = setOf(
        "profiles.json", "disabled_profiles.json", "settings.json", "recent_searches.json", "smart_engines.json",
        "title_engines.json", "ui_state.json", ".wizard_done", "portals.txt", "portal.txt", "api_keys.conf",
        "ultrastalker.db", "manifest.json", "manual_tmdb.json",
    )

    fun readBackup(bytes: ByteArray): Restored {
        if (bytes.size > 128 * 1024 * 1024) throw BackupError("This backup is too large.")
        val files = HashMap<String, ByteArray>()
        try {
            ZipInputStream(bytes.inputStream()).use { zip ->
                while (true) {
                    val e = zip.nextEntry ?: break
                    if (!e.isDirectory) files[e.name] = zip.readBytes()
                }
            }
        } catch (_: Exception) {
            throw BackupError("This file is not a ZIP backup.")
        }
        if (files.isEmpty()) throw BackupError("This file is not a ZIP backup.")
        val manifest = files["manifest.json"]?.let { parseLoose(String(it)) as? JsonObject } ?: throw BackupError("This is not an Ultra Stalker backup (manifest.json is missing).")
        if (manifest.s("product") != "UltraStalker") throw BackupError("This is not an Ultra Stalker backup.")
        val fmt = manifest.s("format").toIntOrNull() ?: 0
        if (fmt < 1 || fmt > 9) throw BackupError("This backup format ($fmt) is not supported yet.")
        for (n in files.keys) if (n !in ALLOWED) throw BackupError("The backup contains an unexpected file: $n")
        val sums = manifest["sha256"] as? JsonObject
        if (fmt >= 6 && sums != null) {
            for ((n, v) in sums) {
                val data = files[n] ?: throw BackupError("The backup is missing $n")
                val got = MessageDigest.getInstance("SHA-256").digest(data).joinToString("") { "%02x".format(it) }
                if (got != (v as? JsonPrimitive)?.content?.lowercase()) throw BackupError("The backup is damaged ($n does not match its fingerprint).")
            }
        }
        val out = mutableListOf<Source>()
        var receiverOnly = 0
        (files["profiles.json"]?.let { parseLoose(String(it)) } as? JsonArray)?.forEach { el ->
            val row = el as? JsonObject ?: return@forEach
            if (row.s("portal").startsWith("file://", true)) receiverOnly++
            fromRow(row)?.let { out += it }
        }
        for (n in listOf("portals.txt", "portal.txt")) files[n]?.let { out += parseText(String(it).removePrefix("\uFEFF")) }
        val disabled = (files["disabled_profiles.json"]?.let { parseLoose(String(it)) } as? JsonArray)?.mapNotNull { k ->
            val a = k as? JsonArray ?: return@mapNotNull null
            if (a.size != 2) null else (a[0] as? JsonPrimitive)?.content.orEmpty().trimEnd('/').lowercase() + "|" + (a[1] as? JsonPrimitive)?.content.orEmpty().uppercase()
        }?.toSet() ?: emptySet()
        return Restored(dedupe(out).filter { it.key !in disabled }, receiverOnly)
    }
}

/* The TV's list of sources, kept in a file. */
class SourceStore(private val file: File) {
    @Synchronized
    fun all(): List<Source> = try {
        (parseLoose(file.readText()) as? JsonArray)?.mapNotNull { (it as? JsonObject)?.let(Sources::fromRow)?.let { s -> s.copy(name = it.s("name")) } } ?: emptyList()
    } catch (_: Exception) {
        emptyList()
    }

    @Synchronized
    fun save(list: List<Source>) {
        file.parentFile?.mkdirs()
        val tmp = File(file.path + ".tmp")
        tmp.writeText(buildJsonArray { Sources.dedupe(list).forEach { add(Sources.toRow(it)) } }.toString())
        tmp.renameTo(file)
    }

    fun add(s: Source) = save(all().filter { it.key != s.key } + s)
    fun remove(key: String) = save(all().filter { it.key != key })
    fun replaceAll(list: List<Source>) = save(list)
}

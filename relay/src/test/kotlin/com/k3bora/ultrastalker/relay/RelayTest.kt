package com.k3bora.ultrastalker.relay

import com.sun.net.httpserver.HttpServer
import java.io.File
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.URL
import java.nio.file.Files
import java.util.Base64
import java.util.concurrent.atomic.AtomicInteger
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class RelayTest {
    private lateinit var upstream: HttpServer
    private lateinit var server: LocalServer
    private lateinit var site: File
    private val links = AtomicInteger()
    private val seen = mutableListOf<String>()
    private lateinit var up: String
    private val movie = ByteArray(5000) { (it % 251).toByte() }

    @BeforeTest
    fun start() {
        upstream = HttpServer.create(InetSocketAddress("0.0.0.0", 0), 0)
        up = "http://127.0.0.1:${upstream.address.port}"
        upstream.createContext("/") { ex ->
            val path = ex.requestURI.path
            synchronized(seen) { seen += ex.requestMethod + " " + ex.requestURI + " cookie=" + (ex.requestHeaders.getFirst("Cookie") ?: "") + " ua=" + (ex.requestHeaders.getFirst("User-Agent") ?: "") + " auth=" + (ex.requestHeaders.getFirst("Authorization") ?: "") + " range=" + (ex.requestHeaders.getFirst("Range") ?: "") }
            fun reply(code: Int, type: String, body: ByteArray, extra: Map<String, String> = emptyMap()) {
                ex.responseHeaders.add("Content-Type", type)
                extra.forEach { (k, v) -> ex.responseHeaders.add(k, v) }
                ex.sendResponseHeaders(code, if (body.isEmpty()) -1 else body.size.toLong())
                if (body.isNotEmpty()) ex.responseBody.write(body)
                ex.close()
            }
            when {
                path == "/portal/load.php" -> {
                    val q = ex.requestURI.query ?: ""
                    when {
                        q.contains("action=handshake") -> reply(200, "application/json", """{"js":{"token":"TOKEN1"}}""".toByteArray())
                        q.contains("action=get_profile") -> reply(200, "application/json", """{"js":{"id":1}}""".toByteArray())
                        q.contains("action=create_link") -> {
                            if (ex.requestHeaders.getFirst("Authorization") != "Bearer TOKEN1") reply(200, "application/json", """{"js":{"error":"auth"}}""".toByteArray())
                            else {
                                val n = links.incrementAndGet()
                                reply(200, "application/json", """{"js":{"cmd":"ffmpeg http://127.0.0.2:${upstream.address.port}/stream/live$n.ts?mac=%mac%"}}""".toByteArray())
                            }
                        }
                        else -> reply(404, "text/plain", "no".toByteArray())
                    }
                }
                path.startsWith("/stream/") -> reply(200, "video/mp2t", ByteArray(188 * 10) { 0x47 })
                path == "/movie.mkv" -> {
                    val r = ex.requestHeaders.getFirst("Range")
                    val m = r?.let { Regex("bytes=(\\d+)-").find(it) }
                    if (m != null) {
                        val a = m.groupValues[1].toInt()
                        reply(206, "video/x-matroska", movie.copyOfRange(a, movie.size), mapOf("Content-Range" to "bytes $a-${movie.size - 1}/${movie.size}", "Accept-Ranges" to "bytes"))
                    } else reply(200, "video/x-matroska", movie, mapOf("Accept-Ranges" to "bytes"))
                }
                path == "/hls/index.m3u8" -> reply(200, "application/vnd.apple.mpegurl", "#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXT-X-KEY:METHOD=AES-128,URI=\"key.bin\"\n#EXTINF:2,\nseg1.ts\n#EXTINF:2,\n/abs/seg2.ts\n".toByteArray())
                path == "/api" -> reply(200, "application/json", """{"ok":1,"method":"${ex.requestMethod}","body":"${String(ex.requestBody.readBytes())}"}""".toByteArray())
                path == "/redirect" -> reply(302, "text/plain", ByteArray(0), mapOf("Location" to "$up/api"))
                else -> reply(404, "text/plain", "nope".toByteArray())
            }
        }
        upstream.start()
        site = Files.createTempDirectory("us-tv-site").toFile()
        File(site, "web").mkdirs()
        File(site, "app").mkdirs()
        File(site, "web/index.html").writeText("<!doctype html><html><head><title>x</title></head><body>hi</body></html>")
        File(site, "app/tv.js").writeText("// tv")
        server = LocalServer(0, FolderSource(site), "9.9.9")
        server.start(5000, false)
    }

    @AfterTest
    fun stop() {
        server.stop()
        upstream.stop(0)
        site.deleteRecursively()
    }

    private val origin get() = "http://127.0.0.1:${server.listeningPort}"
    private fun b64(s: String) = Base64.getUrlEncoder().withoutPadding().encodeToString(s.toByteArray())
    private fun get(path: String, method: String = "GET", body: String? = null, headers: Map<String, String> = emptyMap()): Triple<Int, Map<String, String>, ByteArray> {
        val c = URL(if (path.startsWith("http")) path else origin + path).openConnection() as HttpURLConnection
        c.requestMethod = method
        c.instanceFollowRedirects = false
        headers.forEach { (k, v) -> c.setRequestProperty(k, v) }
        if (body != null) {
            c.doOutput = true
            c.setRequestProperty("Content-Type", "application/json")
            c.outputStream.use { it.write(body.toByteArray()) }
        }
        val code = c.responseCode
        val h = c.headerFields.filterKeys { it != null }.mapKeys { it.key.lowercase() }.mapValues { it.value.joinToString(",") }
        val bytes = (if (code >= 400) c.errorStream else c.inputStream)?.use { it.readBytes() } ?: ByteArray(0)
        return Triple(code, h, bytes)
    }

    @Test
    fun `pages get the TV markers, the bridge first and the features last`() {
        val (code, h, body) = get("/")
        assertEquals(200, code)
        val html = String(body)
        assertTrue(html.indexOf("us-tv") < html.indexOf("<title>"), html)
        assertTrue(html.indexOf("/__app/tv-bridge.js") < html.indexOf("<title>"))
        assertTrue(html.indexOf("/__app/tv.js") > html.indexOf("<title>"))
        assertEquals("same-origin", h["cross-origin-opener-policy"])
        assertEquals("// tv", String(get("/__app/tv.js").third))
        assertTrue(get("/../../etc/passwd").first in 403..404)
        assertTrue(String(get("/config.js").third).contains("relay: \"$origin\""))
    }

    @Test
    fun `p sends the portal's headers, follows redirects and posts bodies`() {
        val h = b64("""{"Cookie":"mac=00:1A:79:00:00:01","User-Agent":"MAG200","Referer":"x"}""")
        val (code, hdr, body) = get("/p?u=" + Relay.enc("$up/redirect") + "&h=" + h)
        assertEquals(200, code)
        assertEquals("$up/api", hdr["x-final-url"])
        assertTrue(String(body).contains("\"method\":\"GET\""))
        val last = synchronized(seen) { seen.last() }
        assertTrue(last.contains("cookie=mac=00:1A:79:00:00:01") && last.contains("ua=MAG200"), last)
        val (_, _, posted) = get("/p?u=" + Relay.enc("$up/api"), "POST", "hello")
        assertTrue(String(posted).contains("\"body\":\"hello\""), String(posted))
        assertEquals(400, get("/p?u=file:///etc/passwd").first)
    }

    @Test
    fun `hls playlists are rewritten so every part goes through the relay`() {
        val (_, _, body) = get("/p?u=" + Relay.enc("$up/hls/index.m3u8") + "&h=" + b64("""{"User-Agent":"X"}"""))
        val text = String(body)
        assertTrue(text.contains("$origin/p?u=" + Relay.enc("$up/hls/seg1.ts") + "&h="), text)
        assertTrue(text.contains(Relay.enc("$up/abs/seg2.ts")), text)
        assertTrue(text.contains("URI=\"$origin/p?u=" + Relay.enc("$up/hls/key.bin")), text)
    }

    @Test
    fun `direct tickets play with ranges`() {
        val t = String(get("/ticket", "POST", """{"mode":"direct","u":"$up/movie.mkv","h":{"User-Agent":"VLC"}}""").third)
        val url = Regex("\"url\":\"([^\"]+)\"").find(t)!!.groupValues[1]
        assertTrue(url.startsWith("$origin/play/") && url.endsWith(".mkv"), url)
        val (code, h, body) = get(url, headers = mapOf("Range" to "bytes=1000-"))
        assertEquals(206, code)
        assertEquals("bytes 1000-4999/5000", h["content-range"])
        assertEquals(4000, body.size)
        assertTrue(body.contentEquals(movie.copyOfRange(1000, 5000)))
        assertEquals(400, get("/ticket", "POST", """{"mode":"x"}""").first)
        assertEquals(403, get("/play/doesnotexist.ts").first)
    }

    @Test
    fun `stalker tickets sign in, ask the portal for a link and keep live links briefly`() {
        val d = """{"mode":"stalker","endpoint":"$up/portal/load.php","mac":"00:1A:79:00:00:01",
            "headers":{"Cookie":"mac=00:1A:79:00:00:01"},"streamHeaders":{"User-Agent":"MAG250"},
            "handshake":{"type":"stb","action":"handshake"},"profile":{"type":"stb","action":"get_profile"},
            "create":{"type":"itv","action":"create_link","cmd":"ffrt http://localhost/ch/1"}}"""
        val url = Regex("\"url\":\"([^\"]+)\"").find(String(get("/ticket", "POST", d).third))!!.groupValues[1]
        val (code, _, body) = get(url)
        assertEquals(200, code)
        assertEquals(1880, body.size)
        assertEquals(1, links.get())
        val streamHit = synchronized(seen) { seen.last { it.contains("/stream/") } }
        assertTrue(streamHit.contains("/stream/live1.ts?mac=00:1A:79:00:00:01") && streamHit.contains("ua=MAG250"), streamHit)
        // the same link is reused right away; ?fresh asks for a new one
        get(url)
        assertEquals(1, links.get())
        get("$url?fresh=1")
        assertEquals(2, links.get())
    }
}

class PhoneLinkTest {
    @Test
    fun `a phone sends a file with the code, gets the TV's files, nothing without the code`() {
        val link = PhoneLink(0)
        val info = link.open()
        try {
            val port = info["port"]!!.toInt()
            val base = "http://127.0.0.1:$port"
            fun call(path: String, body: ByteArray? = null): Pair<Int, String> {
                val c = java.net.URL(base + path).openConnection() as java.net.HttpURLConnection
                if (body != null) {
                    c.requestMethod = "POST"
                    c.doOutput = true
                    c.outputStream.use { it.write(body) }
                }
                val code = c.responseCode
                return code to ((if (code >= 400) c.errorStream else c.inputStream)?.use { String(it.readBytes()) } ?: "")
            }
            val code = link.code
            assertTrue(call("/?c=$code").second.contains("Send to the TV"))
            assertTrue(call("/?c=000").second.contains("Scan the code"))
            assertEquals(403, call("/up?c=000&n=x.zip", "nope".toByteArray()).first)
            assertEquals(null, link.take())
            val up = call("/up?c=$code&n=" + Relay.enc("My backup/1.zip"), "PK-data".toByteArray())
            assertEquals(200, up.first, up.second)
            val got = link.take()!!
            assertEquals("My backup 1.zip", got.first)
            assertEquals("PK-data", String(got.second))
            assertEquals(null, link.take())
            val id = link.offer("UltraStalker-backup.zip", "zip!".toByteArray())
            assertTrue(call("/?c=$code").second.contains("/f/$id?c=$code"))
            assertEquals("zip!", call("/f/$id?c=$code").second)
            assertEquals(403, call("/f/$id?c=1").first)
            assertTrue(PhoneLink.qrSvg("http://192.168.1.5:47391/?c=123456").startsWith("<svg"))
        } finally {
            link.close()
        }
    }
}

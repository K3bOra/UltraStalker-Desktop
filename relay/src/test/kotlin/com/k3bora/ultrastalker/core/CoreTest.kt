package com.k3bora.ultrastalker.core

import com.k3bora.ultrastalker.relay.Relay
import com.sun.net.httpserver.HttpServer
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.OkHttpClient
import java.io.ByteArrayOutputStream
import java.io.File
import java.net.InetSocketAddress
import java.net.URLDecoder
import java.nio.file.Files
import java.security.MessageDigest
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class CoreTest {
    private lateinit var server: HttpServer
    private lateinit var base: String
    private val http = OkHttpClient()
    private val calls = mutableListOf<String>()
    private var tokens = 0
    private var expireOnce = false

    @BeforeTest
    fun start() {
        server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        base = "http://127.0.0.1:${server.address.port}"
        server.createContext("/") { ex ->
            val q = (ex.requestURI.rawQuery ?: "").split("&").filter { it.contains("=") }.associate { it.substringBefore("=") to URLDecoder.decode(it.substringAfter("="), "UTF-8") }
            val auth = ex.requestHeaders.getFirst("Authorization") ?: ""
            synchronized(calls) { calls += ex.requestURI.path + " " + (q["action"] ?: "") + " " + auth + " ua=" + ex.requestHeaders.getFirst("User-Agent") }
            fun send(code: Int, body: String, type: String = "application/json") {
                val b = body.toByteArray()
                ex.responseHeaders.add("Content-Type", type)
                ex.sendResponseHeaders(code, b.size.toLong())
                ex.responseBody.write(b)
                ex.close()
            }
            val path = ex.requestURI.path
            when {
                path == "/stalker_portal/server/load.php" || path == "/portal.php" -> {
                    if (path == "/portal.php") return@createContext send(404, "no")
                    val good = auth == "Bearer T$tokens"
                    when (q["action"]) {
                        "handshake" -> {
                            tokens++
                            send(200, "﻿{\"js\":{\"token\":\"T$tokens\",\"random\":\"r\"}}")
                        }
                        "get_profile" -> send(200, "{\"js\":{\"id\":1,\"status\":0}}")
                        else -> if (!good || expireOnce) {
                            expireOnce = false
                            send(200, "Authorization failed.", "text/plain")
                        } else when (q["action"]) {
                            "get_genres" -> send(200, "{\"js\":[{\"id\":\"*\",\"title\":\"All\"},{\"id\":\"1\",\"title\":\"Sports\"},{\"id\":\"9\",\"title\":\"XXX Adults\"},{\"id\":\"10\",\"title\":\"Kids\",\"censored\":1}]}")
                            "get_categories" -> send(200, "{\"js\":[{\"id\":\"5\",\"title\":\"Action\"}]}")
                            "get_ordered_list" -> if (q["movie_id"]?.contains(":") == true) {
                                send(200, "{\"js\":{\"data\":[{\"id\":\"F${q["movie_id"]!!.substringAfter(":")}\"}]}}")
                            } else if (q["type"] == "series" && q["movie_id"] != "0") {
                                send(200, "{\"js\":{\"total_items\":2,\"max_page_items\":14,\"data\":[{\"id\":\"77:1\",\"name\":\"Season 1\",\"series\":[1,2,3],\"cmd\":\"/media/77.mpg\"},{\"id\":\"77:2\",\"name\":\"Season 2\",\"series\":[1,2],\"cmd\":\"/media/78.mpg\"}]}}")
                            } else if (q["type"] == "itv") {
                                val p = q["p"]!!.toInt()
                                val rows = (1..14).joinToString(",") { i -> val n = (p - 1) * 14 + i; "{\"id\":\"$n\",\"name\":\"Channel $n\",\"number\":\"$n\",\"cmd\":\"ffmpeg http://live/$n.ts\",\"logo\":\"$n.png\",\"use_http_tmp_link\":\"1\"}" }
                                send(200, "{\"js\":{\"total_items\":20,\"max_page_items\":14,\"data\":[$rows,{\"id\":\"99\",\"name\":\"Hot XXX\",\"cmd\":\"x\"}]}}")
                            } else send(200, "{\"js\":{\"total_items\":1,\"max_page_items\":14,\"data\":[{\"id\":\"5\",\"name\":\"Film\",\"cmd\":\"/media/5.mp4\",\"screenshot_uri\":\"/stalker_portal/screenshots/5.jpg\",\"year\":\"2021-01\",\"rating_imdb\":\"7.5\"}]}}")
                            "create_link" -> send(200, "{\"js\":{\"cmd\":\"ffmpeg http://cdn/${q["cmd"]?.substringAfterLast("/")}?series=${q["series"]}\"}}")
                            else -> send(200, "{\"js\":[]}")
                        }
                    }
                }
                path == "/player_api.php" -> {
                    val ua = ex.requestHeaders.getFirst("User-Agent")
                    if (ua.startsWith("VLC")) return@createContext send(200, "[]")
                    when (q["action"]) {
                        "get_live_categories" -> send(200, "[{\"category_id\":\"1\",\"category_name\":\"News\"},{\"category_id\":\"2\",\"category_name\":\"Adult 18+\"}]")
                        "get_live_streams" -> send(200, "[{\"stream_id\":11,\"name\":\"BBC\",\"num\":1,\"stream_icon\":\"http://i/bbc.png\"}]")
                        "get_series_info" -> send(200, "{\"seasons\":[{\"season_number\":1,\"name\":\"First\"}],\"episodes\":{\"2\":[{\"id\":\"502\",\"episode_num\":1,\"title\":\"B1\",\"container_extension\":\"mkv\"}],\"1\":[{\"id\":\"501\",\"episode_num\":1,\"title\":\"A1\",\"container_extension\":\"mp4\"}]}}")
                        else -> send(200, "{\"user_info\":{\"auth\":1,\"status\":\"Active\"}}")
                    }
                }
                path == "/list.m3u" -> send(200, M3U_TEXT, "audio/x-mpegurl")
                else -> send(404, "no")
            }
        }
        server.start()
    }

    @AfterTest
    fun stop() = server.stop(0)

    private val M3U_TEXT = """
        #EXTM3U
        #EXTINF:-1 tvg-logo="http://l/1.png" group-title="News, World",Al Jazeera
        http://s/1.ts
        #EXTINF:-1 group-title="Movies",Inception (2010)
        http://s/inception.mkv
        #EXTINF:-1 group-title="Series",Dark S01E02
        http://s/dark102.mkv
        #EXTINF:-1 group-title="Series",Dark S01E01
        http://s/dark101.mkv
        #EXTINF:-1 group-title="Series",Dark S02E01
        http://s/dark201.mkv
        #EXTINF:-1 group-title="Adults",Something
        http://s/x.ts
        #EXTINF:-1,Plain 24/7
        http://s/plain.ts
    """.trimIndent()

    @Test
    fun stalkerPortalBrowsesAndBuildsTickets() {
        val src = Sources.fromRow(JsonObject(mapOf("portal" to JsonPrimitive("$base/stalker_portal/c/"), "mac" to JsonPrimitive("00-1a-79-aa-bb-cc"))))!!
        assertEquals("00:1A:79:AA:BB:CC", src.mac)
        val p = Stalker(src, http)
        val cats = p.categories(Media.LIVE)
        assertEquals(listOf("All", "Sports"), cats.map { it.title }) // adult and censored folders are gone
        val first = p.page(Media.LIVE, "*", 1)
        assertEquals(14, first.items.size)
        assertTrue(first.hasNext)
        assertEquals("$base/stalker_portal/misc/logos/320/1.png", first.items[0].image)
        assertFalse(p.page(Media.LIVE, "*", 2).hasNext)
        // the session ends: the portal is asked again without an error reaching the screen
        expireOnce = true
        assertEquals("Action", p.categories(Media.MOVIES).single().title)

        val movie = p.page(Media.MOVIES, "5", 1).items.single()
        assertEquals("2021", movie.year)
        assertEquals("$base/stalker_portal/screenshots/5.jpg", movie.image)
        val t = p.ticket(movie)
        assertEquals("stalker", (t["mode"] as JsonPrimitive).content)

        val series = Item("77", "Show", Media.SERIES, raw = JsonObject(mapOf("id" to JsonPrimitive("77"))))
        val seasons = p.seasons(series)
        assertEquals(listOf("1", "2"), seasons.map { it.number })
        assertEquals(3, seasons[0].episodes.size)
        val ep = seasons[1].episodes[1]
        assertEquals("2", ep.number)

        // the relay turns the ticket into a fresh link from the portal
        val relay = Relay()
        val url = relay.ticketUrl(p.ticket(ep), "http://127.0.0.1:1")
        assertTrue(url.startsWith("http://127.0.0.1:1/play/"))
        assertEquals("http://cdn/file_F2.mpg?series=2", relay.stalkerLink(p.ticket(ep)))
        assertTrue(relay.stalkerLink(p.ticket(first.items[0])).startsWith("http://cdn/"))
        assertTrue(calls.all { !it.contains(" create_link ") || it.contains("ua=Mozilla/5.0 (QtEmbedded") })
    }

    @Test
    fun xtreamTriesOtherPlayerNamesAndSortsSeasons() {
        val src = Sources.fromRow(JsonObject(mapOf("portal" to JsonPrimitive("$base/get.php?username=u&password=p%26&type=m3u_plus"), "source_type" to JsonPrimitive("m3u"))))!!
        assertEquals(SourceKind.XTREAM, src.kind)
        val x = Xtream(src, http)
        assertEquals(listOf("News"), x.categories(Media.LIVE).map { it.title })
        val ch = x.page(Media.LIVE, "1", 1).items.single()
        assertEquals("$base/live/u/p%26/11.ts", ch.raw.s("url"))
        val seasons = x.seasons(Item("xt-series-5", "S", Media.SERIES, raw = JsonObject(mapOf("series_id" to JsonPrimitive("5")))))
        assertEquals(listOf("First", "Season 2"), seasons.map { it.title })
        assertEquals("$base/series/u/p%26/502.mkv", seasons[1].episodes[0].raw.s("url"))
        val t = x.ticket(ch)
        assertEquals("IPTVSmartersPlayer", ((t["h"] as JsonObject)["User-Agent"] as JsonPrimitive).content)
    }

    @Test
    fun m3uSortsLiveMoviesAndSeries() {
        val m = M3u(Source("", "$base/list.m3u", Sources.syntheticMac("$base/list.m3u"), SourceKind.M3U), http)
        assertEquals(listOf("News, World", "Other"), m.categories(Media.LIVE).map { it.title })
        assertEquals("http://l/1.png", m.page(Media.LIVE, "*", 1).items[0].image)
        assertEquals(listOf("Inception (2010)"), m.page(Media.MOVIES, "*", 1).items.map { it.title })
        val show = m.page(Media.SERIES, "*", 1).items.single()
        assertEquals("Dark", show.title)
        val seasons = m.seasons(show)
        assertEquals(listOf("1", "2"), seasons.map { it.number })
        assertEquals(listOf("1", "2"), seasons[0].episodes.map { it.number })
        assertEquals(2, m.page(Media.LIVE, "*", 1).items.size) // the adult stream is gone
    }

    @Test
    fun textImportsAndSyntheticMac() {
        val list = Sources.parseText(
            """
            # my portals
            http://one.tv:8080/c/
            00:1A:79:00:00:01  00-1a-79-00-00-02

            http://two.tv/get.php?username=a&password=b&type=m3u
            http://three.tv:80
            username: me
            password: secret
            """.trimIndent(),
        )
        assertEquals(4, list.size)
        assertEquals(listOf(SourceKind.PORTAL, SourceKind.PORTAL, SourceKind.XTREAM, SourceKind.XTREAM), list.map { it.kind })
        assertEquals("http://three.tv:80/get.php?username=me&password=secret&type=m3u_plus&output=ts", list[3].portal)
        // same made-up MAC as the website (02 + sha1)
        val sha = MessageDigest.getInstance("SHA-1").digest("http://x/a.m3u".toByteArray()).joinToString("") { "%02x".format(it) }
        assertEquals(("02" + sha.take(10)).uppercase().chunked(2).joinToString(":"), Sources.syntheticMac("http://x/a.m3u"))
    }

    private fun zip(files: Map<String, String>, manifest: String? = null): ByteArray {
        val out = ByteArrayOutputStream()
        ZipOutputStream(out).use { z ->
            val all = LinkedHashMap(files)
            if (manifest != null) all["manifest.json"] = manifest
            for ((n, v) in all) {
                z.putNextEntry(ZipEntry(n))
                z.write(v.toByteArray())
                z.closeEntry()
            }
        }
        return out.toByteArray()
    }

    @Test
    fun backupFromTheReceiver() {
        val profiles = """[{"name":"Main","portal":"http://a.tv/c/","mac":"00:1A:79:12:34:56"},{"name":"Off","portal":"http://b.tv/c","mac":"00:1A:79:00:00:09"},{"portal":"file:///media/hdd/x.m3u","source_type":"m3u"},{"name":"Line","portal":"http://c.tv/get.php?username=u&password=p","source_type":"m3u","playlist_mode":"xtream"}]"""
        val disabled = """[["http://b.tv/c","00:1A:79:00:00:09"]]"""
        val sum = { s: String -> MessageDigest.getInstance("SHA-256").digest(s.toByteArray()).joinToString("") { "%02x".format(it) } }
        val good = zip(mapOf("profiles.json" to profiles, "disabled_profiles.json" to disabled, "portals.txt" to "http://d.tv/c\n00:1A:79:AB:CD:EF\n"), """{"product":"UltraStalker","format":6,"sha256":{"profiles.json":"${sum(profiles)}"}}""")
        val r = Sources.readBackup(good)
        assertEquals(listOf("Main", "Line", ""), r.sources.map { it.name })
        assertEquals(1, r.receiverOnly)
        assertEquals(SourceKind.XTREAM, r.sources[1].kind)

        assertFailsWith<Sources.BackupError> { Sources.readBackup("hello".toByteArray()) }
        assertFailsWith<Sources.BackupError> { Sources.readBackup(zip(mapOf("profiles.json" to profiles))) }
        val damaged = zip(mapOf("profiles.json" to profiles + " "), """{"product":"UltraStalker","format":6,"sha256":{"profiles.json":"${sum(profiles)}"}}""")
        assertFailsWith<Sources.BackupError> { Sources.readBackup(damaged) }

        val dir = Files.createTempDirectory("us").toFile()
        val store = SourceStore(File(dir, "sources.json"))
        store.replaceAll(r.sources)
        store.add(r.sources[0].copy(name = "Renamed"))
        assertEquals(3, store.all().size)
        assertNotNull(store.all().find { it.name == "Renamed" })
        store.remove(r.sources[0].key)
        assertEquals(2, store.all().size)
    }

    @Test
    fun adultWords() {
        assertTrue(Adult.text("XXX Channels"))
        assertTrue(Adult.text("Movies 18+"))
        assertTrue(Adult.text("قنوات للكبار"))
        assertFalse(Adult.text("Essex News"))
        assertFalse(Adult.text("Sussex 18 Kids"))
        assertFalse(Adult.text("Middlesex"))
    }
}

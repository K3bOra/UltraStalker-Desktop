package com.k3bora.ultrastalker.tv

import androidx.activity.ComponentActivity
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performKeyInput
import androidx.compose.ui.test.pressKey
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.isFocused
import androidx.compose.ui.test.hasAnyDescendant
import com.github.takahirom.roborazzi.captureRoboImage
import com.k3bora.ultrastalker.core.Source
import com.k3bora.ultrastalker.core.SourceKind
import com.k3bora.ultrastalker.core.Sources
import fi.iki.elonen.NanoHTTPD
import org.junit.After
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.ByteArrayOutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/* The screens on a 1080p TV (960×540 dp), driven with the remote's keys. */
@OptIn(ExperimentalTestApi::class)
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w960dp-h540dp-land-television-xhdpi")
class ScreensTest {
    @get:Rule val rule = createAndroidComposeRule<ComponentActivity>()
    private lateinit var server: NanoHTTPD
    private lateinit var base: String
    private lateinit var app: AppState

    @Before
    fun start() {
        server = object : NanoHTTPD("127.0.0.1", 0) {
            override fun serve(session: IHTTPSession): Response {
                val q = session.parms
                fun send(body: String) = newFixedLengthResponse(Response.Status.OK, "application/json", body)
                if (session.uri != "/stalker_portal/server/load.php") return newFixedLengthResponse(Response.Status.NOT_FOUND, "text/plain", "no")
                val names = listOf("Al Jazeera", "BBC News", "beIN Sports 1", "beIN Sports 2", "CNN", "MBC 1", "MBC 2", "MBC Drama", "Nat Geo", "OSN Movies", "Rotana Cinema", "Sky News", "Spacetoon", "TRT Arabi")
                return when (q["action"]) {
                    "handshake" -> send("{\"js\":{\"token\":\"T\"}}")
                    "get_profile" -> send("{\"js\":{\"id\":1}}")
                    "get_genres" -> send("{\"js\":[{\"id\":\"*\",\"title\":\"All\"},{\"id\":\"1\",\"title\":\"Sports\"},{\"id\":\"2\",\"title\":\"News\"},{\"id\":\"3\",\"title\":\"Movies channels\"},{\"id\":\"4\",\"title\":\"Kids\"},{\"id\":\"9\",\"title\":\"Adult XXX\"}]}")
                    "get_categories" -> send("{\"js\":[{\"id\":\"*\",\"title\":\"All\"},{\"id\":\"5\",\"title\":\"Action\"},{\"id\":\"6\",\"title\":\"Arabic\"},{\"id\":\"7\",\"title\":\"Comedy\"}]}")
                    "get_ordered_list" -> if (q["type"] == "itv") {
                        send("{\"js\":{\"total_items\":${names.size},\"max_page_items\":20,\"data\":[" + names.mapIndexed { i, n -> "{\"id\":\"${i + 1}\",\"name\":\"$n\",\"number\":\"${i + 1}\",\"cmd\":\"http://live/${i + 1}.ts\"}" }.joinToString(",") + "]}}")
                    } else if (q["movie_id"] != null && q["movie_id"] != "0") {
                        send("{\"js\":{\"data\":[{\"id\":\"8:1\",\"name\":\"Season 1\",\"series\":[1,2,3,4,5,6]},{\"id\":\"8:2\",\"name\":\"Season 2\",\"series\":[1,2,3,4]}]}}")
                    } else {
                        val films = listOf("The Last Kingdom" to "8.4", "Dune: Part Two" to "8.6", "Oppenheimer" to "8.3", "El Mamar" to "7.9", "Kira & El Gin" to "7.1", "Inception" to "8.8", "Interstellar" to "8.7", "The Batman" to "7.8", "Wonka" to "7.0", "Top Gun: Maverick" to "8.2")
                        send("{\"js\":{\"total_items\":${films.size},\"max_page_items\":20,\"data\":[" + films.mapIndexed { i, (n, r) -> "{\"id\":\"${i + 10}\",\"name\":\"$n\",\"cmd\":\"/media/${i + 10}.mp4\",\"year\":\"20${10 + i}\",\"rating_imdb\":\"$r\",\"description\":\"A story worth watching on a big screen, told with style.\"}" }.joinToString(",") + "]}}")
                    }
                    else -> send("{\"js\":[]}")
                }
            }
        }
        server.start(5000, false)
        base = "http://127.0.0.1:${server.listeningPort}"
        rule.activity.filesDir.resolve("sources.json").delete()
        app = AppState(rule.activity, "2.0.0")
    }

    @After
    fun stop() = server.stop()

    private fun show() = rule.setContent { UltraTheme { Root(app) } }
    private fun key(k: Key, times: Int = 1) = repeat(times) {
        rule.onRoot().performKeyInput { pressKey(k) }
        rule.mainClock.advanceTimeBy(250)
        rule.waitForIdle()
    }
    private fun shot(name: String) {
        rule.mainClock.advanceTimeBy(600)
        rule.waitForIdle()
        rule.onRoot().captureRoboImage("build/screens/$name.png")
    }
    private fun waitText(t: String) = rule.waitUntil(8000) { rule.onAllNodes(hasText(t, substring = true)).fetchSemanticsNodes().isNotEmpty() }
    private fun focusedHas(t: String): Boolean = rule.onAllNodes(isFocused() and (hasText(t, substring = true) or hasAnyDescendant(hasText(t, substring = true)))).fetchSemanticsNodes().isNotEmpty()
    private fun portal() = Source("Home portal", "$base/stalker_portal/c/", "00:1A:79:12:34:56", SourceKind.PORTAL)

    @Test
    fun welcomeAndHome() {
        show()
        shot("01-welcome")
        app.save(listOf(portal(), Source("Family line", "http://line.example.com/get.php?username=a&password=b", Sources.syntheticMac("x"), SourceKind.XTREAM), Source("", "http://lists.example.com/arabic.m3u", Sources.syntheticMac("y"), SourceKind.M3U)))
        rule.waitForIdle()
        app.go(Screen.AddSource)
        rule.waitForIdle()
        app.back()
        rule.waitForIdle()
        shot("02-home")
        assert(focusedHas("Home portal"))
        key(Key.DirectionRight)
        assert(focusedHas("Family line"))
        key(Key.DirectionDown)
        assert(focusedHas("Add a server") || focusedHas("Restore"))
        shot("03-home-moved")
    }

    @Test
    fun browseLiveWithTheRemote() {
        app.save(listOf(portal()))
        app.go(Screen.Browse(app.sources[0]))
        show()
        waitText("Al Jazeera")
        shot("04-live")
        assert(focusedHas("All"))
        key(Key.DirectionDown)
        assert(focusedHas("Sports"))
        key(Key.DirectionRight)
        assert(focusedHas("Al Jazeera"))
        key(Key.DirectionDown, 3)
        assert(focusedHas("beIN Sports 2"))
        shot("05-live-channel")
        // no adult folder
        assert(rule.onAllNodes(hasText("Adult XXX")).fetchSemanticsNodes().isEmpty())
    }

    @Test
    fun moviesAndDetails() {
        app.save(listOf(portal()))
        app.go(Screen.Browse(app.sources[0]))
        show()
        waitText("Al Jazeera")
        key(Key.DirectionUp)
        key(Key.DirectionRight)
        key(Key.Enter)
        waitText("Dune")
        key(Key.DirectionRight)
        assert(focusedHas("The Last Kingdom"))
        key(Key.DirectionRight)
        shot("06-movies")
        key(Key.Enter)
        waitText("Play")
        shot("07-details")
        assert(focusedHas("Play"))
        rule.runOnUiThread { rule.activity.onBackPressedDispatcher.onBackPressed() }
        rule.mainClock.advanceTimeBy(300)
        rule.waitForIdle()
        shot("07b-back")
        assert(focusedHas("Dune"))
    }

    @Test
    fun seriesEpisodes() {
        app.save(listOf(portal()))
        val item = com.k3bora.ultrastalker.core.Item("8", "The Last Kingdom", com.k3bora.ultrastalker.core.Media.SERIES, year = "2015", rating = "8.4", plot = "Uhtred, born a Saxon and raised by Vikings, finds his loyalties tested.")
        app.go(Screen.Details(app.sources[0], item))
        show()
        waitText("EPISODE 1")
        shot("08-series")
        assert(focusedHas("Episode 1"))
        key(Key.DirectionUp)
        key(Key.DirectionRight)
        key(Key.Enter)
        waitText("Episode 4")
        shot("09-season-2")
    }

    @Test
    fun addServer() {
        app.go(Screen.AddSource)
        show()
        shot("10-add")
        key(Key.DirectionDown)
        key(Key.Enter)
        shot("11-add-xtream")
        assert(focusedHas("Xtream"))
    }

    @Test
    fun restoreFound() {
        val zip = ByteArrayOutputStream().also { out ->
            ZipOutputStream(out).use { z ->
                z.putNextEntry(ZipEntry("manifest.json"))
                z.write("{\"product\":\"UltraStalker\",\"format\":5}".toByteArray())
                z.putNextEntry(ZipEntry("profiles.json"))
                z.write("[{\"name\":\"Main\",\"portal\":\"http://a.tv/c/\",\"mac\":\"00:1A:79:12:34:56\"},{\"name\":\"Sport line\",\"portal\":\"http://c.tv/get.php?username=u&password=p\",\"source_type\":\"m3u\",\"playlist_mode\":\"xtream\"}]".toByteArray())
            }
        }.toByteArray()
        val r = Sources.readAny("backup.zip", zip)
        rule.setContent { UltraTheme { RestoreScreen(app, preset = r) } }
        shot("12-restore-found")
        key(Key.Enter)
        assert(app.sources.size == 2)
    }

    @Test
    fun restoreQr() {
        rule.setContent { UltraTheme { RestoreScreen(app) } }
        rule.waitUntil(5000) { true }
        shot("13-restore")
    }
}

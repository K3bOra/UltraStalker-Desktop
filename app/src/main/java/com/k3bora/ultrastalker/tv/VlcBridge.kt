package com.k3bora.ultrastalker.tv

import android.app.Activity
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.widget.FrameLayout
import org.json.JSONArray
import org.json.JSONObject
import org.videolan.libvlc.LibVLC
import org.videolan.libvlc.Media
import org.videolan.libvlc.MediaPlayer
import org.videolan.libvlc.interfaces.IMedia
import org.videolan.libvlc.util.VLCVideoLayout
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/* VLC inside Ultra Stalker for TV.

   The page's player asks window.usNative.vlc (tv-bridge.js → window.USTV, this class)
   the same things it asks VLC in the Windows program: play this link, pause, seek, the
   time, the tracks, and where on the page to show the picture. VLC's picture is a view
   kept exactly over that part of the page; the gold controls stay the page's own. */
class VlcBridge(private val activity: Activity, private val root: FrameLayout, private val web: WebView) {
    private val main = Handler(Looper.getMainLooper())
    private var lib: LibVLC? = null
    private var player: MediaPlayer? = null
    private val video = VLCVideoLayout(activity)
    @Volatile private var error = ""
    @Volatile private var ended = false
    @Volatile private var placed = false

    init {
        video.visibility = View.GONE
        root.addView(video, FrameLayout.LayoutParams(2, 2))
        try {
            val l = LibVLC(activity, arrayListOf("--http-reconnect", "--no-stats", "--audio-time-stretch", "-v"))
            val p = MediaPlayer(l)
            p.attachViews(video, null, true, false)
            p.setEventListener { e ->
                when (e.type) {
                    MediaPlayer.Event.EncounteredError -> error = "VLC couldn't open this stream"
                    MediaPlayer.Event.EndReached -> ended = true
                    MediaPlayer.Event.Playing -> {
                        error = ""
                        ended = false
                    }
                }
            }
            lib = l
            player = p
        } catch (t: Throwable) {
            Log.e("UltraStalker", "VLC failed to start", t)
        }
    }

    private fun <T> onMain(block: () -> T): T? {
        if (Looper.myLooper() == Looper.getMainLooper()) return block()
        var out: T? = null
        val done = CountDownLatch(1)
        main.post {
            try {
                out = block()
            } finally {
                done.countDown()
            }
        }
        done.await(2, TimeUnit.SECONDS)
        return out
    }

    fun pause() = onMain { player?.let { if (it.isPlaying) it.pause() } }

    fun release() {
        onMain {
            player?.let {
                it.stop()
                it.detachViews()
                it.release()
            }
            lib?.release()
            player = null
            lib = null
        }
    }

    /* what window.USTV offers the page */
    inner class Js {
        @JavascriptInterface
        fun vlcAvailable(): Boolean = player != null

        @JavascriptInterface
        fun version(): String = BuildConfigInfo.version(activity)

        @JavascriptInterface
        fun exitApp() {
            main.post { activity.finish() }
        }

        @JavascriptInterface
        fun vlcPlay(json: String): String {
            val o = try {
                JSONObject(json)
            } catch (_: Exception) {
                JSONObject()
            }
            val url = o.optString("url")
            if (!url.startsWith("http://") && !url.startsWith("https://")) return """{"ok":false,"error":"bad link"}"""
            val p = player ?: return """{"ok":false,"error":"VLC isn't available"}"""
            val caching = o.optInt("caching", 3000).coerceIn(300, 20000)
            val volume = if (o.has("volume")) o.optInt("volume", 256) else -1
            val fill = o.optString("fit") == "fill"
            error = ""
            ended = false
            onMain {
                val m = Media(lib, Uri.parse(url))
                m.setHWDecoderEnabled(true, false)
                m.addOption(":network-caching=$caching")
                m.addOption(":http-reconnect")
                p.media = m
                m.release()
                p.videoScale = if (fill) MediaPlayer.ScaleType.SURFACE_FIT_SCREEN else MediaPlayer.ScaleType.SURFACE_BEST_FIT
                p.play()
                if (volume >= 0) p.volume = (volume * 100 / 256).coerceIn(0, 200)
            }
            return JSONObject().put("ok", true).put("version", "libVLC").toString()
        }

        @JavascriptInterface
        fun vlcStop() {
            onMain {
                player?.stop()
                video.visibility = View.GONE
                placed = false
            }
        }

        @JavascriptInterface
        fun vlcCmd(name: String, arg: String): Boolean {
            val p = player ?: return false
            return onMain {
                when (name) {
                    "pause" -> if (p.isPlaying) p.pause()
                    "play" -> if (!p.isPlaying) p.play()
                    "volume" -> p.volume = ((arg.toIntOrNull() ?: 256) * 100 / 256).coerceIn(0, 200)
                    "seek" -> p.time = (arg.toLongOrNull() ?: return@onMain false) * 1000
                    "atrack" -> p.audioTrack = arg.toIntOrNull() ?: return@onMain false
                    "strack" -> p.spuTrack = arg.toIntOrNull() ?: return@onMain false
                    "rate" -> p.rate = (arg.toFloatOrNull() ?: 1f).coerceIn(0.25f, 4f)
                    else -> return@onMain false
                }
                true
            } ?: false
        }

        @JavascriptInterface
        fun vlcStatus(): String {
            val p = player ?: return """{"state":"stopped","time":0,"length":0,"error":"VLC isn't available"}"""
            val state = when (p.playerState) {
                IMedia.State.Playing -> "playing"
                IMedia.State.Paused -> "paused"
                IMedia.State.Opening -> "opening"
                IMedia.State.Ended -> "ended"
                IMedia.State.Error -> "error"
                else -> if (ended) "ended" else "stopped"
            }
            val o = JSONObject()
                .put("state", state)
                .put("time", p.time / 1000.0)
                .put("length", p.length / 1000.0)
                .put("version", "libVLC")
                .put("error", if (state == "error" || state == "stopped") error else "")
            try {
                val v = p.currentVideoTrack
                if (v != null && v.width > 0) {
                    val info = JSONObject().put("width", v.width).put("height", v.height).put("vcodec", codec(v.codec))
                    if (v.frameRateDen > 0) info.put("fps", v.frameRateNum.toDouble() / v.frameRateDen)
                    o.put("info", info)
                }
            } catch (_: Throwable) {
            }
            return o.toString()
        }

        @JavascriptInterface
        fun vlcTracks(): String {
            val p = player ?: return """{"audio":[],"subs":[]}"""
            fun list(tracks: Array<MediaPlayer.TrackDescription>?, cur: Int) = JSONArray().apply {
                tracks?.forEach { put(JSONObject().put("id", it.id).put("name", it.name ?: "Track ${it.id}").put("on", it.id == cur)) }
            }
            return try {
                JSONObject().put("audio", list(p.audioTracks, p.audioTrack)).put("subs", list(p.spuTracks, p.spuTrack)).toString()
            } catch (_: Throwable) {
                """{"audio":[],"subs":[]}"""
            }
        }

        /* page coordinates (CSS pixels, with the page's width) → the screen's pixels */
        @JavascriptInterface
        fun vlcPlace(json: String) {
            main.post {
                if (json.isEmpty()) {
                    video.visibility = View.GONE
                    placed = false
                    return@post
                }
                try {
                    val r = JSONObject(json)
                    val k = web.width.toDouble() / r.optDouble("vw", web.width.toDouble())
                    val lp = FrameLayout.LayoutParams((r.getDouble("w") * k).toInt().coerceAtLeast(2), (r.getDouble("h") * k).toInt().coerceAtLeast(2))
                    lp.leftMargin = (r.getDouble("x") * k).toInt()
                    lp.topMargin = (r.getDouble("y") * k).toInt()
                    video.layoutParams = lp
                    video.visibility = View.VISIBLE
                    video.bringToFront()
                    placed = true
                } catch (_: Exception) {
                }
            }
        }

        @JavascriptInterface
        fun vlcFit(f: String) {
            onMain { player?.videoScale = if (f == "fill") MediaPlayer.ScaleType.SURFACE_FIT_SCREEN else MediaPlayer.ScaleType.SURFACE_BEST_FIT }
        }
    }

    private fun codec(c: String?): String = when (c?.trim()?.lowercase()) {
        "h264", "avc1" -> "h264"
        "hevc", "h265", "hvc1" -> "hevc"
        "mpgv", "mp2v" -> "mpeg2"
        "av01" -> "av1"
        "vp09" -> "vp9"
        else -> c?.trim() ?: ""
    }
}

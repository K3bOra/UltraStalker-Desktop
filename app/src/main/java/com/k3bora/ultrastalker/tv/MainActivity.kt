package com.k3bora.ultrastalker.tv

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.res.AssetManager
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.webkit.ConsoleMessage
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.Toast
import com.k3bora.ultrastalker.relay.FileSource
import com.k3bora.ultrastalker.relay.LocalServer
import java.io.FileNotFoundException
import java.io.InputStream

/* The interface's files, from the APK (assets/site/web, assets/site/app). */
class AssetSource(private val assets: AssetManager) : FileSource {
    override fun open(path: String): InputStream? = try {
        assets.open("site/$path")
    } catch (_: FileNotFoundException) {
        null
    } catch (_: java.io.IOException) {
        null
    }
}

object BuildConfigInfo {
    fun version(c: Context): String = try {
        c.packageManager.getPackageInfo(c.packageName, 0).versionName ?: ""
    } catch (_: Exception) {
        ""
    }
}

/* Ultra Stalker for TV: the local server (interface + relay) and one full-screen page.
   The page is laid out 1280 pixels wide (the computer layout) whatever the screen. */
class MainActivity : Activity() {
    private lateinit var server: LocalServer
    private lateinit var web: WebView
    private lateinit var vlc: VlcBridge
    private lateinit var files: Files
    private var backAt = 0L

    companion object {
        // fixed: the saved sources live in the page's storage, which belongs to this address
        const val PORT = 47390
        const val PAGE_WIDTH = 1280
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON or WindowManager.LayoutParams.FLAG_FULLSCREEN)
        hideBars()

        server = LocalServer(PORT, AssetSource(assets), BuildConfigInfo.version(this))
        try {
            server.start(15000, true)
        } catch (e: Exception) {
            Log.e("UltraStalker", "local server", e)
            server = LocalServer(0, AssetSource(assets), BuildConfigInfo.version(this))
            server.start(15000, true)
        }

        val root = FrameLayout(this)
        root.setBackgroundColor(Color.rgb(9, 9, 10))
        web = WebView(this)
        web.setBackgroundColor(Color.rgb(9, 9, 10))
        root.addView(web, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
        vlc = VlcBridge(this, root, web)
        setContentView(root)

        if (BuildConfig_DEBUG) WebView.setWebContentsDebuggingEnabled(true)
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            mediaPlaybackRequiresUserGesture = false
            useWideViewPort = false
            loadWithOverviewMode = false
            setSupportZoom(false)
            builtInZoomControls = false
            displayZoomControls = false
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            // the interface's files are kept between starts (fast); a new version clears them
            cacheMode = WebSettings.LOAD_DEFAULT
            userAgentString = userAgentString + " UltraStalkerTV/" + BuildConfigInfo.version(this@MainActivity)
        }
        web.isFocusable = true
        web.isFocusableInTouchMode = true
        val prefs = getSharedPreferences("app", MODE_PRIVATE)
        val v = BuildConfigInfo.version(this)
        if (prefs.getString("cachedVersion", "") != v) {
            web.clearCache(true)
            prefs.edit().putString("cachedVersion", v).apply()
        }
        web.addJavascriptInterface(vlc.Js(), "USTV")
        files = Files(this, web)
        web.addJavascriptInterface(files, "USTVFiles")
        web.webChromeClient = object : WebChromeClient() {
            // a file input: the page's own file window (phone or the TV's files)
            override fun onShowFileChooser(view: WebView, callback: android.webkit.ValueCallback<Array<android.net.Uri>>?, params: FileChooserParams?): Boolean {
                callback?.onReceiveValue(null)
                view.evaluateJavascript("window.usTvChooseFile&&usTvChooseFile()", null)
                return true
            }
            override fun onConsoleMessage(m: ConsoleMessage): Boolean {
                Log.d("UltraStalker", "page: ${m.message()} (${m.sourceId()}:${m.lineNumber()})")
                return true
            }
        }
        web.webViewClient = object : WebViewClient() {
            // the app shows only its own pages
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean =
                !request.url.toString().startsWith(server.origin)
        }
        // the computer layout, 1280 pixels wide, on any screen
        root.post {
            val w = root.width.takeIf { it > 0 } ?: resources.displayMetrics.widthPixels
            web.setInitialScale((w * 100.0 / PAGE_WIDTH).toInt())
            web.loadUrl(server.origin + "/index.html")
            web.requestFocus()
        }
    }

    private val BuildConfig_DEBUG get() = (applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0

    @Suppress("DEPRECATION")
    private fun hideBars() {
        window.decorView.systemUiVisibility = (View.SYSTEM_UI_FLAG_FULLSCREEN or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
            or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN)
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideBars()
    }

    /* Back: the page closes what is on top (menu, controls, player, panel); otherwise the
       previous page; at the start, press Back twice to leave. */
    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        web.evaluateJavascript("(function(){try{return !!(window.usTvBack&&window.usTvBack())}catch(e){return false}})()") { handled ->
            if (handled == "true") return@evaluateJavascript
            if (web.canGoBack()) {
                web.goBack()
                return@evaluateJavascript
            }
            val now = System.currentTimeMillis()
            if (now - backAt < 2500) finish()
            else {
                backAt = now
                Toast.makeText(this, "Press Back again to leave · دوس رجوع تاني للخروج", Toast.LENGTH_SHORT).show()
            }
        }
    }

    /* Remote buttons the page knows by name. */
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (event.keyCode == KeyEvent.KEYCODE_BACK || event.keyCode == KeyEvent.KEYCODE_ESCAPE) {
            if (event.action == KeyEvent.ACTION_UP) {
                @Suppress("DEPRECATION")
                onBackPressed()
            }
            return true
        }
        val key = when (event.keyCode) {
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, KeyEvent.KEYCODE_MEDIA_PLAY, KeyEvent.KEYCODE_MEDIA_PAUSE -> "MediaPlayPause"
            KeyEvent.KEYCODE_CHANNEL_UP -> "PageUp"
            KeyEvent.KEYCODE_CHANNEL_DOWN -> "PageDown"
            KeyEvent.KEYCODE_MEDIA_FAST_FORWARD -> "ArrowRight"
            KeyEvent.KEYCODE_MEDIA_REWIND -> "ArrowLeft"
            KeyEvent.KEYCODE_MEDIA_NEXT -> "n"
            KeyEvent.KEYCODE_MEDIA_STOP -> "Escape"
            else -> null
        }
        if (key != null) {
            if (event.action == KeyEvent.ACTION_DOWN) {
                web.evaluateJavascript("(function(){var t=document.activeElement||document.body;t.dispatchEvent(new KeyboardEvent('keydown',{key:'$key',bubbles:true,cancelable:true}))})()", null)
            }
            return true
        }
        return super.dispatchKeyEvent(event)
    }

    override fun onStop() {
        super.onStop()
        // leaving the app (Home): stop the stream, many lines allow one at a time
        web.evaluateJavascript("window.USPlayer&&USPlayer.close()", null)
        vlc.pause()
        web.onPause()
    }

    override fun onStart() {
        super.onStart()
        web.onResume()
        hideBars()
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: android.content.Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == Files.PICK && resultCode == RESULT_OK) files.picked(data?.data)
    }

    override fun onDestroy() {
        files.link.close()
        vlc.release()
        web.destroy()
        server.stop()
        super.onDestroy()
    }
}

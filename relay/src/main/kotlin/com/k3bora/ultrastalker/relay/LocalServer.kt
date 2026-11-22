package com.k3bora.ultrastalker.relay

import fi.iki.elonen.NanoHTTPD
import java.io.File
import java.io.InputStream

/* Where the interface's files come from: the APK's assets on the TV, a folder in tests.
   Paths are relative: "web/index.html", "app/tv.js". */
interface FileSource {
    fun open(path: String): InputStream?
}

class FolderSource(private val root: File) : FileSource {
    override fun open(path: String): InputStream? {
        val f = File(root, path).canonicalFile
        if (!f.path.startsWith(root.canonicalPath + File.separator) || !f.isFile) return null
        return f.inputStream()
    }
}

/* Ultra Stalker for TV — the local server (127.0.0.1 only): the interface, the relay,
   and the few things the TV adds to every page. */
class LocalServer(
    port: Int,
    private val files: FileSource,
    private val version: String,
    private val relay: Relay = Relay(),
) : NanoHTTPD("127.0.0.1", port) {

    val origin: String get() = "http://127.0.0.1:$listeningPort"

    companion object {
        val TYPES = mapOf(
            "html" to "text/html; charset=utf-8", "js" to "text/javascript; charset=utf-8", "mjs" to "text/javascript; charset=utf-8",
            "css" to "text/css; charset=utf-8", "json" to "application/json; charset=utf-8", "webmanifest" to "application/manifest+json",
            "png" to "image/png", "jpg" to "image/jpeg", "jpeg" to "image/jpeg", "webp" to "image/webp", "svg" to "image/svg+xml",
            "ico" to "image/x-icon", "woff2" to "font/woff2", "wasm" to "application/wasm", "txt" to "text/plain; charset=utf-8",
        )
        val ISOLATE = mapOf(
            "Cross-Origin-Opener-Policy" to "same-origin",
            "Cross-Origin-Embedder-Policy" to "credentialless",
            "Cross-Origin-Resource-Policy" to "same-origin",
        )
    }

    private fun status(code: Int): Response.IStatus = Response.Status.lookup(code) ?: object : Response.IStatus {
        override fun getDescription() = "$code Status"
        override fun getRequestStatus() = code
    }

    private fun send(r: Reply): Response {
        val type = r.headers.entries.firstOrNull { it.key.equals("content-type", true) }?.value
        val res = when {
            r.body == null -> newFixedLengthResponse(status(r.status), type, null as InputStream?, 0)
            r.length >= 0 -> newFixedLengthResponse(status(r.status), type, r.body, r.length)
            else -> newChunkedResponse(status(r.status), type, r.body)
        }
        res.setGzipEncoding(false)
        for ((k, v) in r.headers) {
            if (k.equals("content-type", true) || k.equals("content-length", true)) continue
            res.addHeader(k, v)
        }
        return res
    }

    private fun body(session: IHTTPSession): ByteArray? {
        val len = session.headers["content-length"]?.toIntOrNull() ?: return null
        if (len > 1 shl 20) return null
        val buf = ByteArray(len)
        var read = 0
        while (read < len) {
            val n = session.inputStream.read(buf, read, len - read)
            if (n < 0) break
            read += n
        }
        return buf
    }

    private fun query(session: IHTTPSession): Map<String, String> =
        session.parameters.mapValues { it.value.firstOrNull() ?: "" }

    override fun serve(session: IHTTPSession): Response = try {
        handle(session)
    } catch (e: Exception) {
        send(Reply.json(502, kotlinx.serialization.json.buildJsonObject { put("error", kotlinx.serialization.json.JsonPrimitive((e.message ?: e.toString()).take(200))) }))
    }

    private fun handle(session: IHTTPSession): Response {
        val path = session.uri ?: "/"
        val method = session.method.name
        val headers = session.headers
        if (method == "OPTIONS") return send(Reply(204, Reply.CORS))
        when {
            path == "/p" -> return send(relay.proxy(query(session), method, headers, if (method == "POST") body(session) else null, origin))
            path == "/ticket" && method == "POST" -> return send(relay.makeTicket(body(session), origin))
            path == "/health" -> return send(relay.health())
            path.startsWith("/play/") -> {
                val m = Regex("^/play/([A-Za-z0-9_-]+)(?:\\.[a-z0-9]{1,5})?$", RegexOption.IGNORE_CASE).find(path)
                    ?: return send(Reply.text(404, "Not found"))
                return send(relay.play(m.groupValues[1], query(session), method, headers, origin))
            }
            path.startsWith("/tmdb/") -> return send(relay.tmdb(path + (session.queryParameterString?.let { "?$it" } ?: "")))
            path == "/config.js" -> return send(Reply.text(200, "window.US_WEB_CONFIG = { relay: \"$origin\", desktop: \"$version\", tv: true };", "text/javascript; charset=utf-8", ISOLATE + ("Cache-Control" to "no-cache")))
            path == "/coi-sw.js" || path == "/coi.js" -> return send(Reply.text(200, "/* the TV app is isolated by its own server */", "text/javascript; charset=utf-8", ISOLATE))
        }
        var rel = java.net.URLDecoder.decode(path, "UTF-8").trimStart('/')
        if (rel.isEmpty()) rel = "index.html"
        if (rel.split('/').any { it == ".." }) return send(Reply.text(403, "Forbidden"))
        val file = if (rel.startsWith("__app/")) "app/" + rel.removePrefix("__app/") else "web/$rel"
        val ext = rel.substringAfterLast('.', "").lowercase()
        val type = TYPES[ext] ?: "application/octet-stream"
        val input = files.open(file) ?: return send(Reply.text(404, "Not found", extra = ISOLATE))
        if (ext == "html") {
            val html = input.use { it.readBytes().toString(Charsets.UTF_8) }
            return send(Reply.text(200, inject(html), type, ISOLATE + ("Cache-Control" to "no-cache")))
        }
        val bytes = input.use { it.readBytes() }
        return send(Reply(200, ISOLATE + mapOf("Content-Type" to type, "Cache-Control" to "no-cache"), if (method == "HEAD") null else bytes.inputStream(), bytes.size.toLong()))
    }

    /* Every page: "this is the TV app" first (the page reads it as it starts) and the
       remote-control bridge before the player loads; styles and features last. */
    fun inject(html: String): String {
        val first = "<script>document.documentElement.classList.add(\"us-app\",\"us-tv\");window.US_APP={version:\"$version\",tv:true};</script><script src=\"/__app/tv-bridge.js\"></script>"
        val last = "<link rel=\"stylesheet\" href=\"/__app/desktop-app.css\"><link rel=\"stylesheet\" href=\"/__app/tv.css\"><script defer src=\"/__app/features.js\"></script><script defer src=\"/__app/tv.js\"></script>"
        val head = Regex("<head[^>]*>", RegexOption.IGNORE_CASE)
        val withFirst = head.find(html)?.let { html.replaceRange(it.range, it.value + first) } ?: (first + html)
        val at = withFirst.indexOf("</head>", ignoreCase = true)
        return if (at >= 0) withFirst.substring(0, at) + last + withFirst.substring(at) else withFirst + last
    }
}
